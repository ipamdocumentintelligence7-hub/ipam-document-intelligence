# IPAM Document Intelligence System  (Group Six)

Explainable AI-driven document classification, semantic retrieval and decision support - case study: IPAM.

## Quick start (Windows, inside the VS Code terminal)

```
python -m venv venv
venv\Scripts\activate
pip install -r requirements.txt
uvicorn app.main:app --reload
```

Then open **http://127.0.0.1:8000** in Chrome.

Demo logins:  `superadmin / Admin@123`   `staff / Staff@123`   `deptadmin / Dept@123`

For scanned documents install **Tesseract OCR** (see the full guide, Part A, Step 7).
For the real Sentence-BERT search run once: `pip install -r requirements-sbert.txt`

## What is inside

| Folder / file | What it is |
|---|---|
| `app/main.py` | Web server - the API endpoints |
| `app/services.py` | Joins everything: upload -> OCR -> classify -> explain -> save -> search |
| `app/ocr.py` | Reads PDF, DOCX, TXT and scanned images (Tesseract OCR) |
| `app/classifier.py` | TF-IDF + Logistic Regression classifier and LIME explanations |
| `app/search.py` | Sentence-BERT vector search + word-level "why this result?" explanation |
| `app/db.py` | Database layer (SQLite by default, PostgreSQL optional) |
| `frontend/` | The web pages (HTML5, CSS3, JavaScript) |
| `data/training/seed_documents.csv` | Fictional training documents (280) |
| `sample_documents/` | 12 fictional demo files: PDF, DOCX, TXT and scanned PNG/PDF |
| `scripts/evaluate.py` | Produces the test results for Chapter 4 |
| `scripts/make_sample_data.py` | Re-creates the training data and demo files |
| `tests/test_pipeline.py` | Self-test of the whole pipeline |
| `evaluation/` | Test results (report + confusion matrix chart) |

All names and amounts in the sample data are fictional.
