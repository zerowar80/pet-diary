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

from . import ai_providers, auth, database, settings, weather

load_dotenv()

BASE_DIR = Path(__file__).resolve().parent.parent
UPLOAD_DIR = BASE_DIR / "data" / "uploads"
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)

VERSION_FILE = BASE_DIR / "VERSION"
APP_VERSION = VERSION_FILE.read_text().strip() if VERSION_FILE.exists() else "0.0.0"

SESSION_SECRET = os.environ.get("SESSION_SECRET", "dev-only-change-me-in-.env")

app = FastAPI(title="반려견 AI 사진 일기장")
app.add_middleware(SessionMiddleware, secret_key=SESSION_SECRET, same_site="lax")

templates = Jinja2Templates(directory=str(BASE_DIR / "app" / "templates"))
templates.env.globals["AI_PROVIDERS"] = ai_providers.PROVIDERS
templates.env.globals["APP_VERSION"] = APP_VERSION

app.mount("/static", StaticFiles(directory=str(BASE_DIR / "app" / "static")), name="static")
app.mount("/photos", StaticFiles(directory=str(UPLOAD_DIR)), name="photos")


@app.on_event("startup")
def on_startup():
    database.init_db()
    database.ensure_admin_exists()


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

    user_id = database.create_user(username, auth.hash_password(password), is_admin=(database.count_users() == 0))
    request.session["user_id"] = user_id
    database.add_login_record(user_id, username, auth.get_client_ip(request), request.headers.get("user-agent", ""))
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
    database.add_login_record(user["id"], user["username"], auth.get_client_ip(request), request.headers.get("user-agent", ""))
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


# ---------- 설정 (관리자 전용) ----------

@app.get("/settings")
def settings_page(request: Request):
    user = require_login(request)
    if not user:
        return RedirectResponse(url="/login")
    if not user["is_admin"]:
        return RedirectResponse(url="/")

    current_keys = {
        "ANTHROPIC_API_KEY": bool(settings.get("ANTHROPIC_API_KEY")),
        "GOOGLE_API_KEY": bool(settings.get("GOOGLE_API_KEY")),
        "OPENAI_API_KEY": bool(settings.get("OPENAI_API_KEY")),
    }
    guest_mode = settings.get_bool("GUEST_MODE_ENABLED")
    logins = database.list_login_history(100)
    return templates.TemplateResponse(
        "settings.html",
        {
            "request": request, "user": user, "current_keys": current_keys,
            "guest_mode": guest_mode, "logins": logins, "saved": False,
        },
    )


@app.post("/settings/ai-keys")
def settings_ai_keys(
    request: Request,
    anthropic_key: str = Form(""),
    google_key: str = Form(""),
    openai_key: str = Form(""),
):
    user = require_login(request)
    if not user or not user["is_admin"]:
        return RedirectResponse(url="/")
    if anthropic_key.strip():
        database.set_setting("ANTHROPIC_API_KEY", anthropic_key.strip())
    if google_key.strip():
        database.set_setting("GOOGLE_API_KEY", google_key.strip())
    if openai_key.strip():
        database.set_setting("OPENAI_API_KEY", openai_key.strip())
    return RedirectResponse(url="/settings", status_code=303)


@app.post("/settings/guest-mode")
def settings_guest_mode(request: Request, enabled: str = Form("")):
    user = require_login(request)
    if not user or not user["is_admin"]:
        return RedirectResponse(url="/")
    database.set_setting("GUEST_MODE_ENABLED", "1" if enabled == "1" else "0")
    return RedirectResponse(url="/settings", status_code=303)


# ---------- 게스트 모드 (로그인 없이 보기 전용) ----------

@app.get("/guest")
def guest_home(request: Request):
    if not settings.get_bool("GUEST_MODE_ENABLED"):
        return RedirectResponse(url="/login")
    admin = database.get_admin_user()
    if not admin:
        return RedirectResponse(url="/login")
    dogs = database.list_dogs(admin["id"])
    return templates.TemplateResponse(
        "home.html", {"request": request, "dogs": dogs, "user": None, "guest": True}
    )


@app.get("/guest/dog/{dog_id}")
def guest_dog_album(request: Request, dog_id: int):
    if not settings.get_bool("GUEST_MODE_ENABLED"):
        return RedirectResponse(url="/login")
    admin = database.get_admin_user()
    if not admin:
        return RedirectResponse(url="/login")
    dog = database.get_dog(admin["id"], dog_id)
    entries = database.list_entries_for_dog(dog_id) if dog else []
    return templates.TemplateResponse(
        "album.html",
        {
            "request": request, "user": None, "dog": dog, "entries": entries,
            "uploaded": 0, "failed": 0, "guest": True,
        },
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


# ---------- 반려견 등록 ----------

@app.get("/dog/new")
def dog_new_form(request: Request):
    user = require_login(request)
    if not user:
        return RedirectResponse(url="/login")
    return templates.TemplateResponse(
        "dog_new.html", {"request": request, "user": user, "error": None}
    )


@app.post("/dog/new")
def dog_new_submit(request: Request, name: str = Form(...), breed_guess: str = Form("")):
    user = require_login(request)
    if not user:
        return RedirectResponse(url="/login")
    name = name.strip()
    if not name:
        return templates.TemplateResponse(
            "dog_new.html", {"request": request, "user": user, "error": "이름을 입력해주세요."}
        )
    if database.dog_name_exists(user["id"], name):
        return templates.TemplateResponse(
            "dog_new.html",
            {"request": request, "user": user, "error": f"'{name}'은(는) 이미 등록된 이름이에요. 다른 이름을 입력해주세요."},
        )
    dog_id = database.create_dog(user["id"], name, breed_guess.strip() or None)
    return RedirectResponse(url=f"/dog/{dog_id}", status_code=303)


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
    dog_name: str = Form(""),
    ai_provider: str = Form(...),
    auto_identify: str = Form(""),
    photos: list[UploadFile] = None,
):
    user = require_login(request)
    if not user:
        return RedirectResponse(url="/login")

    dog_name = dog_name.strip()
    auto_identify = auto_identify == "1"
    dogs = database.list_dogs(user["id"])
    photos = [p for p in (photos or []) if p and p.filename]

    if not photos:
        return templates.TemplateResponse(
            "upload.html",
            {"request": request, "user": user, "dogs": dogs, "error": "사진을 선택해주세요."},
        )

    identified_tmp_path = None

    if auto_identify:
        candidates = []
        for d in dogs:
            ref_photo = database.get_first_entry_photo(d["id"])
            if ref_photo:
                candidates.append({"name": d["name"], "photo_path": str(UPLOAD_DIR / ref_photo)})

        if not candidates:
            return templates.TemplateResponse(
                "upload.html",
                {
                    "request": request, "user": user, "dogs": dogs,
                    "error": "자동 인식을 쓰려면 사진이 있는 반려견이 최소 하나 있어야 해요. 이름을 직접 입력해주세요.",
                },
            )

        tmp_dir = UPLOAD_DIR / str(user["id"]) / "_tmp"
        tmp_dir.mkdir(parents=True, exist_ok=True)
        tmp_ext = Path(photos[0].filename or "photo.jpg").suffix or ".jpg"
        identified_tmp_path = tmp_dir / f"{uuid.uuid4().hex}{tmp_ext}"
        with identified_tmp_path.open("wb") as f:
            shutil.copyfileobj(photos[0].file, f)

        try:
            identified_name = ai_providers.identify_dog(str(identified_tmp_path), candidates, ai_provider)
        except Exception:  # noqa: BLE001
            identified_name = None

        if not identified_name:
            identified_tmp_path.unlink(missing_ok=True)
            return templates.TemplateResponse(
                "upload.html",
                {
                    "request": request, "user": user, "dogs": dogs,
                    "error": "AI가 확실하게 인식하지 못했어요. 이름을 직접 입력해서 다시 올려주세요.",
                },
            )
        dog_name = identified_name

    if not dog_name:
        return templates.TemplateResponse(
            "upload.html",
            {"request": request, "user": user, "dogs": dogs, "error": "반려견 이름을 입력해주세요."},
        )

    user_folder = UPLOAD_DIR / str(user["id"]) / dog_name
    user_folder.mkdir(parents=True, exist_ok=True)

    dog_id = None
    success_count = 0
    fail_count = 0
    weather_icon = weather.get_current_weather_emoji()

    for index, photo in enumerate(photos):
        ext = Path(photo.filename or "photo.jpg").suffix or ".jpg"
        saved_name = f"{uuid.uuid4().hex}{ext}"
        saved_path = user_folder / saved_name

        if index == 0 and identified_tmp_path is not None:
            shutil.move(str(identified_tmp_path), str(saved_path))
        else:
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
        database.add_entry(dog_id, relative_path, diary_text, ai_provider, weather_icon)

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


# ---------- 월간 하이라이트 ----------

@app.get("/dog/{dog_id}/highlight")
def dog_highlight(request: Request, dog_id: int, month: str = "", provider: str = "claude", generate: int = 0):
    user = require_login(request)
    if not user:
        return RedirectResponse(url="/login")
    dog = database.get_dog(user["id"], dog_id)
    if not dog:
        return RedirectResponse(url="/", status_code=303)

    months = database.list_available_months(dog_id)
    selected_month = month if month in months else (months[0] if months else "")
    entries = database.list_entries_for_dog_month(dog_id, selected_month) if selected_month else []

    summary = None
    error = None
    if selected_month and generate:
        diary_texts = [e["diary_text"] for e in entries if e["diary_text"]]
        if not diary_texts:
            error = "이 달에는 요약할 일기 내용이 없어요."
        else:
            try:
                summary = ai_providers.generate_monthly_highlight(dog["name"], selected_month, diary_texts, provider)
            except Exception as exc:  # noqa: BLE001
                error = f"하이라이트 생성 실패: {exc}"

    return templates.TemplateResponse(
        "highlight.html",
        {
            "request": request, "user": user, "dog": dog,
            "months": months, "selected_month": selected_month,
            "entries": entries, "summary": summary, "error": error,
            "provider": provider,
        },
    )


# ---------- 노래 가사 ----------

@app.get("/dog/{dog_id}/song")
def dog_song(request: Request, dog_id: int, provider: str = "claude", generate: int = 0):
    user = require_login(request)
    if not user:
        return RedirectResponse(url="/login")
    dog = database.get_dog(user["id"], dog_id)
    if not dog:
        return RedirectResponse(url="/", status_code=303)

    entries = database.list_entries_for_dog(dog_id)[:10]
    lyrics = None
    error = None
    if generate:
        diary_texts = [e["diary_text"] for e in entries if e["diary_text"]]
        if not diary_texts:
            error = "아직 일기가 없어서 노래를 만들 수 없어요. 먼저 사진을 올려주세요."
        else:
            try:
                lyrics = ai_providers.generate_song_lyrics(dog["name"], diary_texts, provider)
            except Exception as exc:  # noqa: BLE001
                error = f"노래 생성 실패: {exc}"

    return templates.TemplateResponse(
        "song.html",
        {"request": request, "user": user, "dog": dog, "lyrics": lyrics, "error": error, "provider": provider},
    )
