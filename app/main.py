import os
import shutil
import uuid
from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI, Form, Request, UploadFile
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from starlette.middleware.sessions import SessionMiddleware

from . import ai_providers, auth, database

load_dotenv()

BASE_DIR = Path(__file__).resolve().parent.parent
UPLOAD_DIR = BASE_DIR / "data" / "uploads"
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)

SESSION_SECRET = os.environ.get("SESSION_SECRET", "dev-only-change-me-in-.env")

app = FastAPI(title="반려견 AI 사진 일기장")
app.add_middleware(SessionMiddleware, secret_key=SESSION_SECRET, same_site="lax")

templates = Jinja2Templates(directory=str(BASE_DIR / "app" / "templates"))
templates.env.globals["AI_PROVIDERS"] = ai_providers.PROVIDERS

app.mount("/static", StaticFiles(directory=str(BASE_DIR / "app" / "static")), name="static")
app.mount("/photos", StaticFiles(directory=str(UPLOAD_DIR)), name="photos")


@app.on_event("startup")
def on_startup():
    database.init_db()


def require_login(request: Request):
    """로그인 사용자 정보를 반환하거나, 없으면 None을 반환합니다 (라우트에서 리다이렉트 처리)."""
    return auth.get_current_user(request)


# ---------- 인증 ----------

@app.get("/signup")
def signup_form(request: Request):
    if require_login(request):
        return RedirectResponse(url="/")
    return templates.TemplateResponse("signup.html", {"request": request, "error": None})


@app.post("/signup")
def signup_submit(request: Request, username: str = Form(...), password: str = Form(...), password_confirm: str = Form(...)):
    username = username.strip()
    if len(username) < 2:
        return templates.TemplateResponse(
            "signup.html", {"request": request, "error": "아이디는 2자 이상 입력해주세요."}
        )
    if len(password) < 4:
        return templates.TemplateResponse(
            "signup.html", {"request": request, "error": "비밀번호는 4자 이상 입력해주세요."}
        )
    if password != password_confirm:
        return templates.TemplateResponse(
            "signup.html", {"request": request, "error": "비밀번호가 서로 일치하지 않아요."}
        )
    if database.get_user_by_username(username):
        return templates.TemplateResponse(
            "signup.html", {"request": request, "error": "이미 사용 중인 아이디예요."}
        )

    user_id = database.create_user(username, auth.hash_password(password))
    request.session["user_id"] = user_id
    return RedirectResponse(url="/", status_code=303)


@app.get("/login")
def login_form(request: Request):
    if require_login(request):
        return RedirectResponse(url="/")
    return templates.TemplateResponse("login.html", {"request": request, "error": None})


@app.post("/login")
def login_submit(request: Request, username: str = Form(...), password: str = Form(...)):
    user = database.get_user_by_username(username.strip())
    if not user or not auth.verify_password(password, user["password_hash"]):
        return templates.TemplateResponse(
            "login.html", {"request": request, "error": "아이디 또는 비밀번호가 올바르지 않아요."}
        )
    request.session["user_id"] = user["id"]
    return RedirectResponse(url="/", status_code=303)


@app.get("/logout")
def logout(request: Request):
    request.session.clear()
    return RedirectResponse(url="/login")


@app.get("/account")
def account_form(request: Request):
    user = require_login(request)
    if not user:
        return RedirectResponse(url="/login")
    return templates.TemplateResponse(
        "account.html", {"request": request, "user": user, "error": None, "success": False}
    )


@app.post("/account")
def account_submit(
    request: Request,
    current_password: str = Form(...),
    new_password: str = Form(...),
    new_password_confirm: str = Form(...),
):
    user = require_login(request)
    if not user:
        return RedirectResponse(url="/login")

    if not auth.verify_password(current_password, user["password_hash"]):
        return templates.TemplateResponse(
            "account.html",
            {"request": request, "user": user, "error": "현재 비밀번호가 올바르지 않아요.", "success": False},
        )
    if len(new_password) < 4:
        return templates.TemplateResponse(
            "account.html",
            {"request": request, "user": user, "error": "새 비밀번호는 4자 이상 입력해주세요.", "success": False},
        )
    if new_password != new_password_confirm:
        return templates.TemplateResponse(
            "account.html",
            {"request": request, "user": user, "error": "새 비밀번호가 서로 일치하지 않아요.", "success": False},
        )

    database.update_user_password(user["id"], auth.hash_password(new_password))
    return templates.TemplateResponse(
        "account.html", {"request": request, "user": user, "error": None, "success": True}
    )


# ---------- 홈 ----------

@app.get("/")
def home(request: Request):
    user = require_login(request)
    if not user:
        return RedirectResponse(url="/login")
    dogs = database.list_dogs(user["id"])
    return templates.TemplateResponse(
        "home.html", {"request": request, "dogs": dogs, "user": user}
    )


# ---------- 업로드 ----------

@app.get("/upload")
def upload_form(request: Request):
    user = require_login(request)
    if not user:
        return RedirectResponse(url="/login")
    dogs = database.list_dogs(user["id"])
    return templates.TemplateResponse(
        "upload.html", {"request": request, "user": user, "dogs": dogs, "error": None}
    )


@app.post("/upload")
async def upload_photo(
    request: Request,
    dog_name: str = Form(...),
    ai_provider: str = Form(...),
    photos: list[UploadFile] = None,
):
    user = require_login(request)
    if not user:
        return RedirectResponse(url="/login")

    dog_name = dog_name.strip()
    dogs = database.list_dogs(user["id"])
    photos = [p for p in (photos or []) if p and p.filename]
    if not dog_name or not photos:
        return templates.TemplateResponse(
            "upload.html",
            {"request": request, "user": user, "dogs": dogs, "error": "반려견 이름과 사진을 모두 입력해주세요."},
        )

    user_folder = UPLOAD_DIR / str(user["id"]) / dog_name
    user_folder.mkdir(parents=True, exist_ok=True)

    dog_id = None
    success_count = 0
    fail_count = 0

    for photo in photos:
        ext = Path(photo.filename or "photo.jpg").suffix or ".jpg"
        saved_name = f"{uuid.uuid4().hex}{ext}"
        saved_path = user_folder / saved_name

        with saved_path.open("wb") as f:
            shutil.copyfileobj(photo.file, f)

        try:
            breed_guess, diary_text = ai_providers.generate_diary_entry(str(saved_path), dog_name, ai_provider)
            success_count += 1
        except Exception as exc:  # noqa: BLE001
            breed_guess, diary_text = None, f"(AI 일기 생성 실패: {exc})"
            fail_count += 1

        dog_id = database.get_or_create_dog(user["id"], dog_name, breed_guess)
        relative_path = f"{user['id']}/{dog_name}/{saved_name}"
        database.add_entry(dog_id, relative_path, diary_text, ai_provider)

    if dog_id is None:
        return RedirectResponse(url="/upload", status_code=303)

    redirect_url = f"/dog/{dog_id}?uploaded={success_count}&failed={fail_count}"
    return RedirectResponse(url=redirect_url, status_code=303)


# ---------- 반려견 상세 / 수정 / 삭제 ----------

@app.get("/dog/{dog_id}")
def dog_album(request: Request, dog_id: int, uploaded: int = 0, failed: int = 0):
    user = require_login(request)
    if not user:
        return RedirectResponse(url="/login")
    dog = database.get_dog(user["id"], dog_id)
    entries = database.list_entries_for_dog(dog_id) if dog else []
    return templates.TemplateResponse(
        "album.html",
        {
            "request": request,
            "user": user,
            "dog": dog,
            "entries": entries,
            "uploaded": uploaded,
            "failed": failed,
        },
    )


@app.get("/dog/{dog_id}/edit")
def dog_edit_form(request: Request, dog_id: int):
    user = require_login(request)
    if not user:
        return RedirectResponse(url="/login")
    dog = database.get_dog(user["id"], dog_id)
    return templates.TemplateResponse(
        "dog_edit.html", {"request": request, "user": user, "dog": dog, "error": None}
    )


@app.post("/dog/{dog_id}/edit")
def dog_edit_submit(request: Request, dog_id: int, name: str = Form(...), breed_guess: str = Form("")):
    user = require_login(request)
    if not user:
        return RedirectResponse(url="/login")
    name = name.strip()
    dog = database.get_dog(user["id"], dog_id)
    if not name:
        return templates.TemplateResponse(
            "dog_edit.html", {"request": request, "user": user, "dog": dog, "error": "이름을 입력해주세요."}
        )
    database.update_dog(user["id"], dog_id, name, breed_guess.strip() or None)
    return RedirectResponse(url=f"/dog/{dog_id}", status_code=303)


@app.post("/dog/{dog_id}/delete")
def dog_delete(request: Request, dog_id: int):
    user = require_login(request)
    if not user:
        return RedirectResponse(url="/login")
    dog = database.get_dog(user["id"], dog_id)
    if dog:
        dog_folder = UPLOAD_DIR / str(user["id"]) / dog["name"]
        shutil.rmtree(dog_folder, ignore_errors=True)
        database.delete_dog(user["id"], dog_id)
    return RedirectResponse(url="/", status_code=303)


@app.post("/entry/{entry_id}/delete")
def entry_delete(request: Request, entry_id: int):
    user = require_login(request)
    if not user:
        return RedirectResponse(url="/login")
    entry = database.get_entry(entry_id)
    if entry:
        dog = database.get_dog(user["id"], entry["dog_id"])
        if dog:
            photo_file = UPLOAD_DIR / entry["photo_path"]
            photo_file.unlink(missing_ok=True)
            database.delete_entry(entry_id)
            return RedirectResponse(url=f"/dog/{dog['id']}", status_code=303)
    return RedirectResponse(url="/", status_code=303)
