"""
services.py - The "brain" that joins everything together:
OCR -> classification -> explanation -> repository -> semantic search -> admin tools.
The web API (main.py) only calls the functions in this file.
"""
import csv
import io
import json
import secrets
import shutil
import uuid
from pathlib import Path

from . import config
from .classifier import DocClassifier, load_seed_data
from .db import Database, now
from .ocr import extract_text, split_passages, tesseract_status
from .search import VectorIndex
from .security import hash_password, verify_password


class ServiceError(Exception):
    def __init__(self, message, status=400):
        super().__init__(message)
        self.message, self.status = message, status


class Services:
    def __init__(self, db_url=None):
        for folder in (config.UPLOAD_DIR, config.MODEL_DIR):
            folder.mkdir(parents=True, exist_ok=True)
        self.db = Database(db_url or config.DATABASE_URL)
        self.db.create_tables()
        self._seed_defaults()
        self.clf = DocClassifier()
        if not self.clf.load():
            self.retrain(None)
        self.index = VectorIndex(self.db, load_seed_data()[0])
        self.index.rebuild()

    # ------------------------------------------------------------------ setup
    def _seed_defaults(self):
        for cat in config.DEFAULT_CATEGORIES:
            if not self.db.one("SELECT id FROM categories WHERE name = ?", (cat,)):
                self.db.insert("INSERT INTO categories (name, active, created_at) VALUES (?, 1, ?)", (cat, now()))
        demo = [("superadmin", "System SuperAdmin", "Admin@123", "super_admin"),
                ("staff", "Administrative Staff Demo", "Staff@123", "admin_staff"),
                ("deptadmin", "Departmental Admin Demo", "Dept@123", "dept_admin")]
        if not self.db.one("SELECT id FROM users LIMIT 1"):
            for u, n, p, r in demo:
                self.db.insert("INSERT INTO users (username, full_name, password_hash, role, active, created_at) "
                               "VALUES (?, ?, ?, ?, 1, ?)", (u, n, hash_password(p), r, now()))

    def audit(self, username, action, detail=""):
        self.db.insert("INSERT INTO audit_logs (username, action, detail, created_at) VALUES (?, ?, ?, ?)",
                       (username, action, str(detail)[:500], now()))

    # ------------------------------------------------------------------- auth
    def login(self, username, password):
        u = self.db.one("SELECT * FROM users WHERE username = ?", (username.strip(),))
        if not u or not u["active"] or not verify_password(password, u["password_hash"]):
            self.audit(username, "LOGIN_FAILED")
            raise ServiceError("Wrong username or password.", 401)
        token = secrets.token_urlsafe(32)
        self.db.execute("INSERT INTO sessions (token, user_id, created_at) VALUES (?, ?, ?)", (token, u["id"], now()))
        self.audit(u["username"], "LOGIN")
        return token, self.public_user(u)

    def user_from_token(self, token):
        if not token:
            return None
        row = self.db.one("SELECT u.* FROM sessions s JOIN users u ON u.id = s.user_id WHERE s.token = ?", (token,))
        return row if row and row["active"] else None

    def logout(self, token):
        self.db.execute("DELETE FROM sessions WHERE token = ?", (token,))

    @staticmethod
    def public_user(u):
        return {"id": u["id"], "username": u["username"], "full_name": u["full_name"], "role": u["role"],
                "role_label": config.ROLES.get(u["role"], u["role"]), "active": bool(u["active"])}

    # ------------------------------------------------------------- categories
    def categories(self, only_active=False):
        sql = "SELECT id, name, active FROM categories" + (" WHERE active = 1" if only_active else "") + " ORDER BY id"
        return [{"id": c["id"], "name": c["name"], "active": bool(c["active"])} for c in self.db.query(sql)]

    # -------------------------------------------------- upload + analyse (XAI)
    def analyze_upload(self, filename, data: bytes, user):
        ext = Path(filename).suffix.lower()
        if ext not in config.ALLOWED_EXT:
            raise ServiceError("File type not supported. Use PDF, DOCX, TXT, PNG, JPG or TIFF.")
        if len(data) > config.MAX_UPLOAD_MB * 1024 * 1024:
            raise ServiceError("File is too large (maximum %d MB)." % config.MAX_UPLOAD_MB)
        stored = uuid.uuid4().hex + ext
        path = config.UPLOAD_DIR / stored
        path.write_bytes(data)
        try:
            text, method, ocr_conf = extract_text(path)
        except Exception as exc:
            path.unlink(missing_ok=True)
            if exc.__class__.__name__ == "OCRUnavailable":
                raise ServiceError(str(exc), 503)
            raise ServiceError("Could not read this file: %s" % exc)
        if len(text.strip()) < 10:
            path.unlink(missing_ok=True)
            raise ServiceError("No readable text was found in this file.")
        pred = self.clf.predict(text)
        expl = self.clf.explain(text, pred["category"])
        expl["probabilities"] = pred["probabilities"]
        doc_id = self.db.insert(
            "INSERT INTO documents (filename, stored_name, file_type, text, predicted_category, confidence, final_category, "
            "status, ocr_method, ocr_confidence, explanation_json, uploaded_by, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?, NULL, 'pending', ?, ?, ?, ?, ?)",
            (filename, stored, ext.lstrip("."), text, pred["category"], pred["confidence"], method, ocr_conf,
             json.dumps(expl), user["username"], now()))
        self.audit(user["username"], "CLASSIFY", "doc %d '%s' -> %s (%.0f%%) via %s; explanation: %s" % (
            doc_id, filename, pred["category"], pred["confidence"] * 100, method, expl["method"]))
        return self.get_document(doc_id)

    def save_document(self, doc_id, category, user):
        doc = self.db.one("SELECT * FROM documents WHERE id = ?", (doc_id,))
        if not doc:
            raise ServiceError("Document not found.", 404)
        if doc["status"] == "saved":
            raise ServiceError("This document is already in the repository.")
        valid = [c["name"] for c in self.categories(only_active=True)]
        if category not in valid:
            raise ServiceError("Unknown or inactive category.")
        self.db.execute("UPDATE documents SET final_category = ?, status = 'saved', saved_at = ? WHERE id = ?",
                        (category, now(), doc_id))
        self.index.add_passages(doc_id, split_passages(doc["text"]))
        overridden = category != doc["predicted_category"]
        self.audit(user["username"], "SAVE", "doc %d saved as '%s'%s" % (
            doc_id, category, " (staff OVERRODE AI suggestion '%s')" % doc["predicted_category"] if overridden else ""))
        return self.get_document(doc_id)

    def delete_document(self, doc_id, user):
        doc = self.db.one("SELECT * FROM documents WHERE id = ?", (doc_id,))
        if not doc:
            raise ServiceError("Document not found.", 404)
        self.db.execute("DELETE FROM chunks WHERE document_id = ?", (doc_id,))
        self.db.execute("DELETE FROM documents WHERE id = ?", (doc_id,))
        (config.UPLOAD_DIR / doc["stored_name"]).unlink(missing_ok=True)
        if doc["status"] == "saved":
            self.index.rebuild()
        self.audit(user["username"], "DELETE", "doc %d '%s'" % (doc_id, doc["filename"]))

    # ------------------------------------------------------------- repository
    @staticmethod
    def _doc_view(d, full=False):
        v = {"id": d["id"], "filename": d["filename"], "file_type": d["file_type"], "status": d["status"],
             "predicted_category": d["predicted_category"], "final_category": d["final_category"],
             "confidence": d["confidence"], "ocr_method": d["ocr_method"], "ocr_confidence": d["ocr_confidence"],
             "uploaded_by": d["uploaded_by"], "created_at": d["created_at"], "saved_at": d["saved_at"],
             "low_confidence": (d["confidence"] or 0) < config.LOW_CONFIDENCE}
        if full:
            v["text"] = d["text"]
            v["explanation"] = json.loads(d["explanation_json"] or "{}")
        return v

    def get_document(self, doc_id):
        d = self.db.one("SELECT * FROM documents WHERE id = ?", (doc_id,))
        if not d:
            raise ServiceError("Document not found.", 404)
        return self._doc_view(d, full=True)

    def list_documents(self, category=None, status="saved"):
        sql, params = "SELECT * FROM documents WHERE status = ?", [status]
        if category:
            sql += " AND final_category = ?"
            params.append(category)
        return [self._doc_view(d) for d in self.db.query(sql + " ORDER BY id DESC", tuple(params))]

    def file_path(self, doc_id):
        d = self.db.one("SELECT filename, stored_name FROM documents WHERE id = ?", (doc_id,))
        if not d:
            raise ServiceError("Document not found.", 404)
        return config.UPLOAD_DIR / d["stored_name"], d["filename"]

    # ----------------------------------------------------------------- search
    def search(self, query, top_k, category, user):
        query = (query or "").strip()
        if len(query) < 2:
            raise ServiceError("Type a longer search question.")
        allowed = None
        if category:
            allowed = {r["id"] for r in self.db.query("SELECT id FROM documents WHERE status='saved' AND final_category = ?", (category,))}
        hits = self.index.search(query, max(1, min(int(top_k or 5), 20)), allowed)
        results = []
        for rank, h in enumerate(hits, 1):
            d = self.db.one("SELECT * FROM documents WHERE id = ?", (h["document_id"],))
            if not d:
                continue
            v = self._doc_view(d)
            v.update({"rank": rank, "score": round(h["score"], 4), "passage": h["passage"]})
            results.append(v)
        self.audit(user["username"], "SEARCH", "'%s' -> %d result(s)" % (query, len(results)))
        return {"query": query, "engine": self.index.embedder.name, "results": results}

    def explain_search(self, query, doc_id, user):
        hits = self.index.search(query, 1, {doc_id})
        if not hits:
            raise ServiceError("No passage found for this document.", 404)
        ex = self.index.explain(query, hits[0]["passage"])
        ex.update({"passage": hits[0]["passage"], "score": round(hits[0]["score"], 4), "engine": self.index.embedder.name})
        self.audit(user["username"], "EXPLAIN_SEARCH", "query '%s' doc %d" % (query, doc_id))
        return ex

    def export_csv(self, query, top_k, category, user):
        res = self.search(query, top_k, category, user)
        buf = io.StringIO()
        w = csv.writer(buf)
        w.writerow(["Rank", "Filename", "Category", "Similarity score", "AI confidence", "Best matching passage"])
        for r in res["results"]:
            w.writerow([r["rank"], r["filename"], r["final_category"], r["score"], round(r["confidence"], 3), r["passage"]])
        self.audit(user["username"], "EXPORT", "search summary for '%s'" % query)
        return buf.getvalue()

    # ------------------------------------------------------------------ admin
    def system_info(self):
        return {"database": self.db.kind, "embedding_engine": self.index.embedder.name,
                "ocr": tesseract_status(), "model": self.clf.meta, "indexed_passages": len(self.index.texts)}

    def stats(self):
        per = self.db.query("SELECT final_category AS name, COUNT(*) AS n FROM documents WHERE status='saved' GROUP BY final_category")
        pending = self.db.one("SELECT COUNT(*) AS n FROM documents WHERE status='pending'")["n"]
        low = self.db.one("SELECT COUNT(*) AS n FROM documents WHERE confidence < ?", (config.LOW_CONFIDENCE,))["n"]
        return {"saved": sum(p["n"] for p in per), "pending": pending, "low_confidence": low, "per_category": per}

    def list_users(self):
        return [self.public_user(u) for u in self.db.query("SELECT * FROM users ORDER BY id")]

    def create_user(self, username, full_name, password, role, admin):
        if role not in config.ROLES:
            raise ServiceError("Invalid role.")
        if len(username.strip()) < 3 or len(password) < 6:
            raise ServiceError("Username needs 3+ characters and password 6+ characters.")
        if self.db.one("SELECT id FROM users WHERE username = ?", (username.strip(),)):
            raise ServiceError("That username already exists.")
        self.db.insert("INSERT INTO users (username, full_name, password_hash, role, active, created_at) VALUES (?, ?, ?, ?, 1, ?)",
                       (username.strip(), full_name, hash_password(password), role, now()))
        self.audit(admin["username"], "USER_CREATE", "%s as %s" % (username, role))

    def update_user(self, user_id, role, active, password, admin, username=None, full_name=None):
        u = self.db.one("SELECT * FROM users WHERE id = ?", (user_id,))
        if not u:
            raise ServiceError("User not found.", 404)
        if u["id"] == admin["id"] and (active is False or (role and role != "super_admin")):
            raise ServiceError("You cannot remove your own SuperAdmin access.")
        if username is not None and username.strip() != u["username"]:
            username = username.strip()
            if len(username) < 3:
                raise ServiceError("Username needs 3+ characters.")
            if self.db.one("SELECT id FROM users WHERE username = ?", (username,)):
                raise ServiceError("That username already exists.")
            self.db.execute("UPDATE users SET username = ? WHERE id = ?", (username, user_id))
        if full_name is not None and full_name.strip():
            self.db.execute("UPDATE users SET full_name = ? WHERE id = ?", (full_name.strip(), user_id))
        if role:
            if role not in config.ROLES:
                raise ServiceError("Invalid role.")
            self.db.execute("UPDATE users SET role = ? WHERE id = ?", (role, user_id))
        if active is not None:
            self.db.execute("UPDATE users SET active = ? WHERE id = ?", (1 if active else 0, user_id))
        if password:
            if len(password) < 6:
                raise ServiceError("Password needs 6+ characters.")
            self.db.execute("UPDATE users SET password_hash = ? WHERE id = ?", (hash_password(password), user_id))
        self.audit(admin["username"], "USER_UPDATE", "%s -> username=%s name=%s role=%s active=%s pw_reset=%s" % (u["username"], username, full_name, role, active, bool(password)))

    def add_category(self, name, admin):
        name = name.strip()
        if len(name) < 3:
            raise ServiceError("Category name is too short.")
        if self.db.one("SELECT id FROM categories WHERE name = ?", (name,)):
            raise ServiceError("Category already exists.")
        self.db.insert("INSERT INTO categories (name, active, created_at) VALUES (?, 1, ?)", (name, now()))
        self.audit(admin["username"], "CATEGORY_ADD", name)

    def set_category_active(self, cat_id, active, admin):
        self.db.execute("UPDATE categories SET active = ? WHERE id = ?", (1 if active else 0, cat_id))
        self.audit(admin["username"], "CATEGORY_TOGGLE", "id %s active=%s" % (cat_id, active))

    def logs(self, limit=200):
        return self.db.query("SELECT username, action, detail, created_at FROM audit_logs ORDER BY id DESC LIMIT ?", (limit,))

    def retrain(self, admin):
        """Retrain on the seed data + every document staff have confirmed (learning from human decisions)."""
        texts, labels = load_seed_data()
        active = {c["name"] for c in self.categories(only_active=True)}
        for d in self.db.query("SELECT text, final_category FROM documents WHERE status='saved'"):
            texts.append(d["text"])
            labels.append(d["final_category"])
        pairs = [(t, l) for t, l in zip(texts, labels) if l in active]
        if len({l for _, l in pairs}) < 2:
            raise ServiceError("Need examples from at least two active categories to train.")
        meta = self.clf.train([p[0] for p in pairs], [p[1] for p in pairs])
        self.audit(admin["username"] if admin else "system", "RETRAIN", json.dumps(meta))
        return meta
