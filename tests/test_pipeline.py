"""
Quick self-test of the whole pipeline (no web server needed).
Run:  python tests/test_pipeline.py
"""
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from app import config                       # noqa: E402
from app.services import Services, ServiceError   # noqa: E402

tmp = Path(tempfile.mkdtemp())
config.UPLOAD_DIR = tmp / "uploads"
config.MODEL_DIR = tmp / "models"
svc = Services("sqlite:///" + str(tmp / "test.db").replace("\\", "/"))
ok = 0


def check(name, cond):
    global ok
    print(("PASS  " if cond else "FAIL  ") + name)
    ok += bool(cond)
    if not cond:
        sys.exit(1)


token, user = svc.login("staff", "Staff@123")
check("login works", user["role"] == "admin_staff")
try:
    svc.login("staff", "wrong")
    check("wrong password rejected", False)
except ServiceError:
    check("wrong password rejected", True)

truth = {}
for line in (ROOT / "sample_documents" / "ground_truth.csv").read_text().splitlines()[1:]:
    f, c = line.split(",")
    truth[f] = c
correct = 0
for f, cat in truth.items():
    d = svc.analyze_upload(f, (ROOT / "sample_documents" / f).read_bytes(), user)
    correct += d["predicted_category"] == cat
    svc.save_document(d["id"], d["predicted_category"], user)
check("classified %d/%d sample documents correctly" % (correct, len(truth)), correct >= len(truth) - 1)
check("repository holds all saved documents", len(svc.list_documents()) == len(truth))

admin = svc.user_from_token(svc.login("deptadmin", "Dept@123")[0])
for q, expect in [("unpaid tuition balance and receipts", "Financial Records"),
                  ("examination timetable for lecturers", "Administrative Memos"),
                  ("offer of admission to new applicants", "Admission"),
                  ("student grades and GPA", "Transcripts")]:
    res = svc.search(q, 3, None, admin)
    print("   ", q, "->", [(r["final_category"], r["score"]) for r in res["results"]])
    check("search '%s' top hit is %s" % (q, expect), res["results"][0]["final_category"] == expect)
ex = svc.explain_search("unpaid tuition balance and receipts", res["results"][0]["id"], admin)
check("search explanation returns terms", len(ex["terms"]) > 0)
check("CSV export works", "Rank" in svc.export_csv("examination timetable", 3, None, admin))
check("stats work", svc.stats()["saved"] == len(truth))
sa = svc.user_from_token(svc.login("superadmin", "Admin@123")[0])
check("retrain works", "samples" in svc.retrain(sa))
check("audit log has entries", len(svc.logs()) > 10)
print("\nAll %d checks passed. Embedding engine: %s" % (ok, svc.index.embedder.name))
