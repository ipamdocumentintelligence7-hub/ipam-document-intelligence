"""
evaluate.py - Objective 4: "Test the performance of the proposed system using sample data".
Run:  python scripts/evaluate.py
Creates the files in the evaluation/ folder that you paste into Chapter 4 / 5.
"""
import csv
import random
import sys
import tempfile
import time
from difflib import SequenceMatcher
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

from sklearn.metrics import accuracy_score, classification_report, confusion_matrix   # noqa: E402
from sklearn.model_selection import train_test_split                                   # noqa: E402

from app import config                                   # noqa: E402
from app.classifier import build_pipeline, load_seed_data  # noqa: E402
from app.ocr import extract_text, split_passages          # noqa: E402
from app.search import VectorIndex                        # noqa: E402
from app.db import Database                               # noqa: E402

OUT = ROOT / "evaluation"
OUT.mkdir(exist_ok=True)
rng = random.Random(11)
report = []


def say(line=""):
    print(line)
    report.append(line)


def degrade(text, rate):
    """Simulate OCR errors: randomly damage characters."""
    chars = list(text)
    for i in range(len(chars)):
        if chars[i].isalpha() and rng.random() < rate:
            chars[i] = rng.choice("aeiorlnt1|")
    return "".join(chars)


# ---------------------------------------------------------------- 1. classification
texts, labels = load_seed_data()
xtr, xte, ytr, yte = train_test_split(texts, labels, test_size=0.25, random_state=1, stratify=labels)
model = build_pipeline().fit(xtr, ytr)
say("=" * 70)
say("1. DOCUMENT CLASSIFICATION  (train %d docs / test %d docs)" % (len(xtr), len(xte)))
say("=" * 70)
for name, test in [("Clean text", xte), ("Noisy text (5% OCR-style character errors)", [degrade(t, 0.05) for t in xte]),
                   ("Very noisy text (12% character errors)", [degrade(t, 0.12) for t in xte])]:
    pred = model.predict(test)
    say("%-48s accuracy = %.3f" % (name, accuracy_score(yte, pred)))
pred = model.predict(xte)
say("")
say(classification_report(yte, pred, digits=3))
classes = sorted(set(labels))
cm = confusion_matrix(yte, pred, labels=classes)
say("Confusion matrix (rows = true, columns = predicted): " + str(classes))
say(str(cm))
try:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    fig, ax = plt.subplots(figsize=(6, 5))
    ax.imshow(cm, cmap="Blues")
    ax.set_xticks(range(len(classes)))
    ax.set_xticklabels(classes, rotation=30, ha="right")
    ax.set_yticks(range(len(classes)))
    ax.set_yticklabels(classes)
    for i in range(len(classes)):
        for j in range(len(classes)):
            ax.text(j, i, cm[i, j], ha="center", va="center")
    ax.set_xlabel("Predicted")
    ax.set_ylabel("True")
    ax.set_title("Confusion matrix (test set)")
    fig.tight_layout()
    fig.savefig(OUT / "confusion_matrix.png", dpi=150)
    say("Saved evaluation/confusion_matrix.png")
except Exception as exc:
    say("(chart skipped: %s)" % exc)

# timing
t0 = time.time()
for t in xte[:50]:
    model.predict_proba([t])
say("Average classification time: %.1f ms per document" % ((time.time() - t0) / 50 * 1000))

# ---------------------------------------------------------------- 2. OCR
say("")
say("=" * 70)
say("2. OCR / DOCUMENT INGESTION  (sample_documents/)")
say("=" * 70)
rows = []
for line in (ROOT / "sample_documents" / "ground_truth.csv").read_text().splitlines()[1:]:
    fname, cat = line.split(",")
    path = ROOT / "sample_documents" / fname
    t0 = time.time()
    try:
        text, method, conf = extract_text(path)
    except Exception as exc:
        say("%-40s FAILED: %s" % (fname, exc))
        continue
    truth = (ROOT / "sample_documents" / "_truth" / (fname + ".txt")).read_text(encoding="utf-8")
    sim = SequenceMatcher(None, " ".join(truth.split()), " ".join(text.split())).ratio()
    rows.append((fname, method, sim, conf, time.time() - t0))
    say("%-40s %-18s text similarity %.3f  OCR conf %s  %.1fs" % (fname, method, sim, "-" if conf is None else "%.0f%%" % conf, time.time() - t0))
ocr_rows = [r for r in rows if r[1].startswith("OCR")]
if ocr_rows:
    say("Average text similarity on scanned files: %.3f  (1.000 = perfect)" % np.mean([r[2] for r in ocr_rows]))

# ---------------------------------------------------------------- 3. semantic search
say("")
say("=" * 70)
say("3. SEMANTIC SEARCH  (relevance = document is in the expected category)")
say("=" * 70)
tmp = Path(tempfile.mkdtemp())
db = Database("sqlite:///" + str(tmp / "eval.db").replace("\\", "/"))
db.create_tables()
from datetime import datetime  # noqa: E402
corpus_texts, corpus_labels = xte, yte   # documents the model never trained on
for t, l in zip(corpus_texts, corpus_labels):
    did = db.insert("INSERT INTO documents (filename, text, final_category, status, created_at) VALUES (?, ?, ?, 'saved', ?)",
                    ("eval", t, l, str(datetime.now())))
    for i, p in enumerate(split_passages(t)):
        db.insert("INSERT INTO chunks (document_id, chunk_index, text) VALUES (?, ?, ?)", (did, i, p))
index = VectorIndex(db, xtr)
index.rebuild()
say("Search engine used: " + index.embedder.name)
say("Indexed: %d documents, %d passages" % (len(corpus_texts), len(index.texts)))
queries = [
    ("students who have not paid their tuition", "Financial Records"), ("receipt for payment of examination fee", "Financial Records"),
    ("supplier invoice for printer paper", "Financial Records"), ("quarterly income and expenditure of the institute", "Financial Records"),
    ("grades and GPA of a student", "Transcripts"), ("official results for the semester", "Transcripts"),
    ("courses taken and marks obtained", "Transcripts"), ("academic record of a diploma student", "Transcripts"),
    ("letter offering a place on a programme", "Admission"), ("application form for new applicants", "Admission"),
    ("entry requirements and WASSCE results", "Admission"), ("admission committee decisions", "Admission"),
    ("notice about a staff meeting", "Administrative Memos"), ("instruction to lecturers about submitting grades", "Administrative Memos"),
    ("public holiday closure of the institute", "Administrative Memos"), ("memo from the registrar to all staff", "Administrative Memos"),
]
doc_cat = {r["id"]: r["final_category"] for r in db.query("SELECT id, final_category FROM documents")}
k, p_at_k, rr, times = 5, [], [], []
for q, cat in queries:
    t0 = time.time()
    hits = index.search(q, k)
    times.append(time.time() - t0)
    rel = [doc_cat[h["document_id"]] == cat for h in hits]
    p_at_k.append(sum(rel) / k)
    rr.append(next((1 / (i + 1) for i, r in enumerate(rel) if r), 0.0))
    say("  %-55s P@5=%.2f  top hit %s" % (q, p_at_k[-1], "correct" if rel and rel[0] else "WRONG"))
say("Mean Precision@%d = %.3f" % (k, np.mean(p_at_k)))
say("Mean Reciprocal Rank (MRR) = %.3f" % np.mean(rr))
say("Average search time = %.1f ms" % (np.mean(times) * 1000))

(OUT / "evaluation_report.txt").write_text("\n".join(report), encoding="utf-8")
print("\nSaved evaluation/evaluation_report.txt")
