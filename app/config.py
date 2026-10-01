"""
config.py  -  All settings live here.
You can change any of them without touching the code by creating a file called
.env in the project folder (copy .env.example to .env and edit it).
"""
import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent


def _load_env_file():
    """Read simple KEY=VALUE lines from the .env file (if it exists)."""
    env_path = BASE_DIR / ".env"
    if not env_path.exists():
        return
    for line in env_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


_load_env_file()

DATA_DIR = BASE_DIR / "data"
UPLOAD_DIR = DATA_DIR / "uploads"
MODEL_DIR = DATA_DIR / "models"
SEED_CSV = DATA_DIR / "training" / "seed_documents.csv"
FRONTEND_DIR = BASE_DIR / "frontend"

# Database: SQLite by default (zero setup). For PostgreSQL put this in .env:
# DATABASE_URL=postgresql://postgres:YOURPASSWORD@localhost:5432/ipam_docs
DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///" + str(DATA_DIR / "ipam_docs.db").replace("\\", "/"))

# Embeddings: "auto" = try Sentence-BERT, fall back to LSA. Or force "sbert" / "lsa".
EMBEDDING_BACKEND = os.getenv("EMBEDDING_BACKEND", "auto").lower()
SBERT_MODEL = os.getenv("SBERT_MODEL", "sentence-transformers/all-MiniLM-L6-v2")

# OCR: path to tesseract.exe on Windows (only needed if it is not found automatically)
TESSERACT_CMD = os.getenv("TESSERACT_CMD", "")

LOW_CONFIDENCE = float(os.getenv("LOW_CONFIDENCE", "0.50"))   # below this -> "please review manually"
MAX_UPLOAD_MB = int(os.getenv("MAX_UPLOAD_MB", "15"))
MAX_OCR_PAGES = int(os.getenv("MAX_OCR_PAGES", "10"))
CHUNK_WORDS = 90                                              # words per searchable passage
ALLOWED_EXT = {".pdf", ".docx", ".txt", ".png", ".jpg", ".jpeg", ".tif", ".tiff", ".bmp"}

DEFAULT_CATEGORIES = ["Transcripts", "Admission", "Administrative Memos", "Financial Records"]

# Who may do what (taken from Section 4.1 of the proposal). Change here if needed.
ROLES = {
    "admin_staff": "Administrative Staff",
    "dept_admin": "Departmental Admin",
    "super_admin": "System SuperAdmin",
}
PERMISSIONS = {
    "upload":  {"admin_staff", "super_admin"},                 # upload, view classification + XAI, save
    "repo":    {"admin_staff", "dept_admin", "super_admin"},   # view repository / documents
    "search":  {"dept_admin", "super_admin"},                  # semantic search, ranked results, export
    "manage":  {"super_admin"},                                # users, categories, logs, retrain
}
