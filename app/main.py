"""
main.py - The web server (FastAPI). Each function below is one "API endpoint" that the
web page (frontend) talks to. Start it with:  uvicorn app.main:app --reload
"""
from contextlib import asynccontextmanager
from typing import Optional

from fastapi import Depends, FastAPI, File, Header, HTTPException, UploadFile
from fastapi.responses import FileResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from . import config
from .services import ServiceError, Services

STATE = {}


@asynccontextmanager
async def lifespan(app):
    print("Starting IPAM Document Intelligence System ... (first start trains the model, please wait)")
    STATE["svc"] = Services()
    print("Ready. Open http://127.0.0.1:8000 in your browser.")
    yield


app = FastAPI(title="IPAM Document Intelligence System", version="1.0", lifespan=lifespan)


@app.exception_handler(ServiceError)
async def service_error_handler(request, exc: ServiceError):
    return JSONResponse(status_code=exc.status, content={"detail": exc.message})


def svc() -> Services:
    return STATE["svc"]


# ------------------------------------------------------------------ security
def current_user(authorization: Optional[str] = Header(None)):
    token = (authorization or "").replace("Bearer ", "").strip()
    user = svc().user_from_token(token)
    if not user:
        raise HTTPException(status_code=401, detail="Please log in again.")
    user["token"] = token
    return user


def need(permission: str):
    def checker(user=Depends(current_user)):
        if user["role"] not in config.PERMISSIONS[permission]:
            raise HTTPException(status_code=403, detail="Your role (%s) is not allowed to do this." % config.ROLES[user["role"]])
        return user
    return checker


# -------------------------------------------------------------------- models
class LoginIn(BaseModel):
    username: str
    password: str


class SaveIn(BaseModel):
    category: str


class SearchIn(BaseModel):
    query: str
    top_k: int = 5
    category: Optional[str] = None


class ExplainIn(BaseModel):
    query: str
    document_id: int


class UserIn(BaseModel):
    username: str
    full_name: str = ""
    password: str
    role: str


class UserUpdateIn(BaseModel):
    username: Optional[str] = None
    full_name: Optional[str] = None
    role: Optional[str] = None
    active: Optional[bool] = None
    password: Optional[str] = None


class CategoryIn(BaseModel):
    name: str


class ActiveIn(BaseModel):
    active: bool


# ---------------------------------------------------------------------- auth
@app.post("/api/auth/login")
def login(body: LoginIn):
    token, user = svc().login(body.username, body.password)
    return {"token": token, "user": user}


@app.post("/api/auth/logout")
def logout(user=Depends(current_user)):
    svc().logout(user["token"])
    return {"ok": True}


@app.get("/api/auth/me")
def me(user=Depends(current_user)):
    return svc().public_user(user)


@app.get("/api/system")
def system_info(user=Depends(current_user)):
    return svc().system_info()


@app.get("/api/stats")
def stats(user=Depends(current_user)):
    return svc().stats()


@app.get("/api/categories")
def categories(user=Depends(current_user)):
    return svc().categories(only_active=True)


# ------------------------------------------------- upload / classify / save
@app.post("/api/documents/analyze")
def analyze(file: UploadFile = File(...), user=Depends(need("upload"))):
    data = file.file.read()
    return svc().analyze_upload(file.filename or "upload", data, user)


@app.post("/api/documents/{doc_id}/save")
def save_doc(doc_id: int, body: SaveIn, user=Depends(need("upload"))):
    return svc().save_document(doc_id, body.category, user)


@app.delete("/api/documents/{doc_id}")
def delete_doc(doc_id: int, user=Depends(need("upload"))):
    svc().delete_document(doc_id, user)
    return {"ok": True}


@app.get("/api/documents")
def list_docs(category: Optional[str] = None, status: str = "saved", user=Depends(need("repo"))):
    return svc().list_documents(category, status)


@app.get("/api/documents/{doc_id}")
def get_doc(doc_id: int, user=Depends(need("repo"))):
    return svc().get_document(doc_id)


@app.get("/api/documents/{doc_id}/download")
def download(doc_id: int, user=Depends(need("repo"))):
    path, name = svc().file_path(doc_id)
    if not path.exists():
        raise HTTPException(status_code=404, detail="Original file is missing on disk.")
    return FileResponse(str(path), filename=name)


# -------------------------------------------------------------------- search
@app.post("/api/search")
def search(body: SearchIn, user=Depends(need("search"))):
    return svc().search(body.query, body.top_k, body.category, user)


@app.post("/api/search/explain")
def search_explain(body: ExplainIn, user=Depends(need("search"))):
    return svc().explain_search(body.query, body.document_id, user)


@app.post("/api/search/export")
def search_export(body: SearchIn, user=Depends(need("search"))):
    csv_text = svc().export_csv(body.query, body.top_k, body.category, user)
    return Response(content=csv_text, media_type="text/csv",
                    headers={"Content-Disposition": "attachment; filename=search_summary.csv"})


# --------------------------------------------------------------------- admin
@app.get("/api/admin/users")
def admin_users(user=Depends(need("manage"))):
    return svc().list_users()


@app.post("/api/admin/users")
def admin_create_user(body: UserIn, user=Depends(need("manage"))):
    svc().create_user(body.username, body.full_name, body.password, body.role, user)
    return {"ok": True}


@app.patch("/api/admin/users/{user_id}")
def admin_update_user(user_id: int, body: UserUpdateIn, user=Depends(need("manage"))):
    svc().update_user(user_id, body.role, body.active, body.password, user, body.username, body.full_name)
    return {"ok": True}


@app.get("/api/admin/categories")
def admin_categories(user=Depends(need("manage"))):
    return svc().categories()


@app.post("/api/admin/categories")
def admin_add_category(body: CategoryIn, user=Depends(need("manage"))):
    svc().add_category(body.name, user)
    return {"ok": True}


@app.patch("/api/admin/categories/{cat_id}")
def admin_toggle_category(cat_id: int, body: ActiveIn, user=Depends(need("manage"))):
    svc().set_category_active(cat_id, body.active, user)
    return {"ok": True}


@app.get("/api/admin/logs")
def admin_logs(user=Depends(need("manage"))):
    return svc().logs()


@app.post("/api/admin/retrain")
def admin_retrain(user=Depends(need("manage"))):
    return svc().retrain(user)


# ------------------------------------------------------------ the web pages
app.mount("/", StaticFiles(directory=str(config.FRONTEND_DIR), html=True), name="frontend")
