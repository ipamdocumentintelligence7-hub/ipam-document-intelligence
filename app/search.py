"""
search.py - Vector-based semantic search + explanations.

1. Every saved document is cut into short passages.
2. Each passage is turned into a vector (an "embedding") by Sentence-BERT.
   If Sentence-BERT is not installed / cannot be downloaded, a lighter LSA model is used instead.
3. A query is embedded the same way; passages are ranked by cosine similarity
   (identical maths to a FAISS IndexFlatIP flat index).
4. Explanation: words are removed one at a time from the best passage; a big drop in
   similarity means that word mattered (perturbation / occlusion explanation).
"""
import re
import threading

import numpy as np

from . import config

WORD = re.compile(r"[A-Za-z][A-Za-z0-9'/-]+")


class SBERTEmbedder:
    def __init__(self, model_name):
        from sentence_transformers import SentenceTransformer
        self.model = SentenceTransformer(model_name)
        self.name = "Sentence-BERT (" + model_name.split("/")[-1] + ")"
        self.needs_fit = False

    def fit(self, corpus):
        pass

    def encode(self, texts):
        v = self.model.encode(list(texts), batch_size=64, normalize_embeddings=True, show_progress_bar=False)
        return np.asarray(v, dtype="float32")


def _stem_tokens(text):
    """Lower-case words with a very simple stemmer (offered/offers -> offer)."""
    from sklearn.feature_extraction.text import ENGLISH_STOP_WORDS
    out = []
    for w in re.findall(r"[a-z][a-z0-9]+", text.lower()):
        if w in ENGLISH_STOP_WORDS:
            continue
        for suf in ("ations", "ation", "ing", "ed", "es", "s"):
            if w.endswith(suf) and len(w) - len(suf) >= 4:
                w = w[: -len(suf)]
                break
        out.append(w)
    return out


class LSAEmbedder:
    """Fallback: TF-IDF followed by SVD (Latent Semantic Analysis). Needs no downloads."""
    def __init__(self):
        self.name = "LSA fallback (TF-IDF + SVD)"
        self.needs_fit = True
        self.vec = self.svd = None

    def fit(self, corpus):
        from sklearn.decomposition import TruncatedSVD
        from sklearn.feature_extraction.text import TfidfVectorizer
        self.vec = TfidfVectorizer(sublinear_tf=True, analyzer=_stem_tokens, min_df=2)
        x = self.vec.fit_transform(corpus)
        k = max(2, min(120, x.shape[1] - 1, x.shape[0] - 1))
        self.svd = TruncatedSVD(n_components=k, random_state=1).fit(x)

    def encode(self, texts):
        z = self.svd.transform(self.vec.transform(list(texts)))
        n = np.linalg.norm(z, axis=1, keepdims=True)
        n[n == 0] = 1.0
        return (z / n).astype("float32")


def make_embedder():
    mode = config.EMBEDDING_BACKEND
    if mode in ("auto", "sbert"):
        try:
            return SBERTEmbedder(config.SBERT_MODEL)
        except Exception as exc:
            print("[search] Sentence-BERT not available (%s). Using LSA fallback." % exc.__class__.__name__)
            if mode == "sbert":
                print("[search] EMBEDDING_BACKEND=sbert was requested but could not be loaded.")
    return LSAEmbedder()


class VectorIndex:
    def __init__(self, db, seed_texts):
        self.db = db
        self.lock = threading.RLock()
        self.seed_texts = seed_texts
        self.embedder = make_embedder()
        self.chunk_ids, self.doc_ids, self.texts = [], [], []
        self.matrix = np.zeros((0, 1), dtype="float32")

    def rebuild(self):
        """Load every passage of every SAVED document and embed it."""
        with self.lock:
            rows = self.db.query(
                "SELECT c.id, c.document_id, c.text FROM chunks c JOIN documents d ON d.id = c.document_id "
                "WHERE d.status = 'saved' ORDER BY c.id")
            self.chunk_ids = [r["id"] for r in rows]
            self.doc_ids = [r["document_id"] for r in rows]
            self.texts = [r["text"] for r in rows]
            if self.embedder.needs_fit:
                self.embedder.fit(self.seed_texts + self.texts)
            self.matrix = self.embedder.encode(self.texts) if self.texts else np.zeros((0, 1), dtype="float32")

    def add_passages(self, doc_id, passages):
        """Store passages of a newly saved document and add them to the index."""
        ids = []
        for i, p in enumerate(passages):
            ids.append(self.db.insert("INSERT INTO chunks (document_id, chunk_index, text) VALUES (?, ?, ?)", (doc_id, i, p)))
        self.rebuild() if self.embedder.needs_fit else self._append(ids, doc_id, passages)

    def _append(self, ids, doc_id, passages):
        with self.lock:
            if not passages:
                return
            vecs = self.embedder.encode(passages)
            self.chunk_ids += ids
            self.doc_ids += [doc_id] * len(ids)
            self.texts += passages
            self.matrix = vecs if self.matrix.shape[0] == 0 else np.vstack([self.matrix, vecs])

    def remove_document(self, doc_id):
        self.db.execute("DELETE FROM chunks WHERE document_id = ?", (doc_id,))
        self.rebuild()

    def search(self, query, top_k=5, allowed_doc_ids=None):
        """Return [{document_id, score, passage}] best passage per document."""
        with self.lock:
            if self.matrix.shape[0] == 0:
                return []
            q = self.embedder.encode([query])[0]
            sims = self.matrix @ q
            best = {}
            for i in np.argsort(-sims):
                d = self.doc_ids[i]
                if allowed_doc_ids is not None and d not in allowed_doc_ids:
                    continue
                if d not in best:
                    best[d] = {"document_id": d, "score": float(sims[i]), "passage": self.texts[i]}
                if len(best) >= top_k:
                    break
            return list(best.values())

    def explain(self, query, passage, max_words=120):
        """Which words in `passage` make it similar to `query`? (occlusion method)"""
        with self.lock:
            words = list(dict.fromkeys(w for w in WORD.findall(passage) if len(w) > 2))[:max_words]
            q = self.embedder.encode([query])[0]
            base = float(self.embedder.encode([passage])[0] @ q)
            variants = []
            for w in words:
                variants.append(re.sub(r"\b" + re.escape(w) + r"\b", " ", passage))
            scores = self.embedder.encode(variants) @ q if variants else []
            terms = [{"word": w, "score": round(base - float(s), 4)} for w, s in zip(words, scores)]
            terms = [t for t in terms if t["score"] > 0]
            terms.sort(key=lambda t: -t["score"])
            return {"method": "Word-removal (occlusion) similarity drop", "base_similarity": round(base, 4),
                    "terms": terms[:12]}
