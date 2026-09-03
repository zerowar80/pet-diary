import os
import shutil
import tempfile
import uuid
import zipfile
from datetime import datetime, timedelta
from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI, Form, Request, UploadFile
from fastapi.responses import FileResponse, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from starlette.background import BackgroundTask
from starlette.middleware.sessions import SessionMiddleware

from . import ai_providers, auth, database, polaroid, settings, video_utils, weather

load_dotenv()

BASE_DIR = Path(__file__).resolve().parent.parent
UPLOAD_DIR = BASE_DIR / "data" / "uploads"
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)

VERSION_FILE = BASE_DIR / "VERSION"
APP_VERSION = VERSION_FILE.read_text().strip() if VERSION_FILE.exists() else "0.0.0"

SESSION_SECRET = os.environ.get("SESSION_SECRET", "dev-only-change-me-in-.env")
REACTION_EMOJIS = ["❤️", "😆", "😮", "😢", "👍"]

app = FastAPI(title="반려견 AI 사진 일기장")
app.add_middleware(SessionMiddleware, secret_key=SESSION_SECRET, same_site="lax")

templates = Jinja2Templates(directory=str(BASE_DIR / "app" / "templates"))
templates.env.globals["AI_PROVIDERS"] = ai_providers.PROVIDERS
templates.env.globals["APP_VERSION"] = APP_VERSION
templates.env.globals["site_title"] = lambda: settings.get("SITE_TITLE", "우리 아이 일기장")
templates.env.globals["current_theme"] = lambda: settings.get("THEME", "dark_umber")
templates.env.globals["REACTION_EMOJIS"] = REACTION_EMOJIS


def _has_new_notice(request: Request) -> bool:
    user = auth.get_current_user(request)
    if not user:
        return False
    latest = database.get_latest_notice_created_at()
    if not latest:
        return False
    last_seen = database.get_notices_last_seen(user["id"])
    if not last_seen:
        return True
    return latest > last_seen


templates.env.globals["has_new_notice"] = _has_new_notice


def _has_new_member(request: Request) -> bool:
    user = auth.get_current_user(request)
    if not user or not user["is_admin"]:
        return False
    latest = database.get_latest_member_created_at(user["id"])
    if not latest:
        return False
    last_seen = database.get_members_last_seen(user["id"])
    if not last_seen:
        return True
    return latest > last_seen


templates.env.globals["has_new_member"] = _has_new_member


def _unread_message_count(request: Request) -> int:
    user = auth.get_current_user(request)
    if not user:
        return 0
    if not database.get_message_notifications_enabled(user["id"]):
        return 0
    return database.count_unread_messages(user["id"])


templates.env.globals["unread_message_count"] = _unread_message_count

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
    signup_open = database.count_users() == 0 or settings.get_bool("SIGNUP_ENABLED", default=True)
    return templates.TemplateResponse("signup.html", {"request": request, "error": None, "closed": not signup_open})


@app.post("/signup")
def signup_submit(request: Request, username: str = Form(...), password: str = Form(...), password_confirm: str = Form(...)):
    signup_open = database.count_users() == 0 or settings.get_bool("SIGNUP_ENABLED", default=True)
    if not signup_open:
        return templates.TemplateResponse(
            "signup.html", {"request": request, "error": None, "closed": True}
        )

    username = username.strip()
    if len(username) < 2:
        return templates.TemplateResponse(
            "signup.html", {"request": request, "error": "아이디는 2자 이상 입력해주세요.", "closed": False}
        )
    if len(password) < 4:
        return templates.TemplateResponse(
            "signup.html", {"request": request, "error": "비밀번호는 4자 이상 입력해주세요.", "closed": False}
        )
    if password != password_confirm:
        return templates.TemplateResponse(
            "signup.html", {"request": request, "error": "비밀번호가 서로 일치하지 않아요.", "closed": False}
        )
    if database.get_user_by_username(username):
        return templates.TemplateResponse(
            "signup.html", {"request": request, "error": "이미 사용 중인 아이디예요.", "closed": False}
        )

    user_id = database.create_user(username, auth.hash_password(password), is_admin=(database.count_users() == 0))
    request.session["user_id"] = user_id
    database.add_login_record(user_id, username, auth.get_client_ip(request), request.headers.get("user-agent", ""))
    redirect_to = request.session.pop("post_login_redirect", None)
    return RedirectResponse(url=redirect_to or "/", status_code=303)


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
    redirect_to = request.session.pop("post_login_redirect", None)
    return RedirectResponse(url=redirect_to or "/", status_code=303)


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
        "account.html",
        {
            "request": request, "user": user, "error": None, "success": False,
            "comment_notifications_enabled": database.get_comment_notifications_enabled(user["id"]),
            "message_notifications_enabled": database.get_message_notifications_enabled(user["id"]),
        },
    )


@app.post("/account/message-notifications")
def account_message_notifications(request: Request, message_notifications: str = Form("")):
    user = require_login(request)
    if not user:
        return RedirectResponse(url="/login")
    database.set_message_notifications_enabled(user["id"], message_notifications == "1")
    return RedirectResponse(url="/account", status_code=303)


@app.post("/account/delete")
def account_delete(request: Request, password: str = Form(...)):
    user = require_login(request)
    if not user:
        return RedirectResponse(url="/login")
    if not auth.verify_password(password, user["password_hash"]):
        return templates.TemplateResponse(
            "account.html",
            {
                "request": request, "user": user, "error": "비밀번호가 올바르지 않아 탈퇴할 수 없어요.", "success": False,
                "comment_notifications_enabled": database.get_comment_notifications_enabled(user["id"]),
                "message_notifications_enabled": database.get_message_notifications_enabled(user["id"]),
            },
        )
    if user["is_admin"] and database.count_admins() <= 1:
        return templates.TemplateResponse(
            "account.html",
            {
                "request": request, "user": user,
                "error": "마지막 남은 관리자 계정이라 탈퇴할 수 없어요. 다른 계정을 관리자로 먼저 지정해주세요.",
                "success": False,
                "comment_notifications_enabled": database.get_comment_notifications_enabled(user["id"]),
                "message_notifications_enabled": database.get_message_notifications_enabled(user["id"]),
            },
        )
    shutil.rmtree(UPLOAD_DIR / str(user["id"]), ignore_errors=True)
    database.delete_user(user["id"])
    request.session.clear()
    return RedirectResponse(url="/login", status_code=303)


@app.post("/account/notifications")
def account_notifications(request: Request, comment_notifications: str = Form("")):
    user = require_login(request)
    if not user:
        return RedirectResponse(url="/login")
    database.set_comment_notifications_enabled(user["id"], comment_notifications == "1")
    return RedirectResponse(url="/account", status_code=303)


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
    notif = database.get_comment_notifications_enabled(user["id"])
    msg_notif = database.get_message_notifications_enabled(user["id"])

    if not auth.verify_password(current_password, user["password_hash"]):
        return templates.TemplateResponse(
            "account.html",
            {"request": request, "user": user, "error": "현재 비밀번호가 올바르지 않아요.", "success": False, "comment_notifications_enabled": notif, "message_notifications_enabled": msg_notif},
        )
    if len(new_password) < 4:
        return templates.TemplateResponse(
            "account.html",
            {"request": request, "user": user, "error": "새 비밀번호는 4자 이상 입력해주세요.", "success": False, "comment_notifications_enabled": notif, "message_notifications_enabled": msg_notif},
        )
    if new_password != new_password_confirm:
        return templates.TemplateResponse(
            "account.html",
            {"request": request, "user": user, "error": "새 비밀번호가 서로 일치하지 않아요.", "success": False, "comment_notifications_enabled": notif, "message_notifications_enabled": msg_notif},
        )

    database.update_user_password(user["id"], auth.hash_password(new_password))
    return templates.TemplateResponse(
        "account.html", {"request": request, "user": user, "error": None, "success": True, "comment_notifications_enabled": notif, "message_notifications_enabled": msg_notif}
    )


# ---------- 설정 (관리자 전용) ----------

@app.get("/settings")
def settings_page(request: Request):
    user = require_login(request)
    if not user:
        return RedirectResponse(url="/login")
    if not user["is_admin"]:
        return RedirectResponse(url="/")

    database.update_members_last_seen(user["id"])

    current_keys = {
        "ANTHROPIC_API_KEY": bool(settings.get("ANTHROPIC_API_KEY")),
        "GOOGLE_API_KEY": bool(settings.get("GOOGLE_API_KEY")),
        "OPENAI_API_KEY": bool(settings.get("OPENAI_API_KEY")),
    }
    guest_mode = settings.get_bool("GUEST_MODE_ENABLED")
    signup_enabled = settings.get_bool("SIGNUP_ENABLED", default=True)
    current_site_title = settings.get("SITE_TITLE", "우리 아이 일기장")
    current_theme_value = settings.get("THEME", "dark_umber")
    current_diary_voice = settings.get("DIARY_VOICE", "guardian")
    logins = database.list_login_history(100)
    members = database.list_users()
    admin_count = database.count_admins()
    return templates.TemplateResponse(
        "settings.html",
        {
            "request": request, "user": user, "current_keys": current_keys,
            "guest_mode": guest_mode, "signup_enabled": signup_enabled,
            "current_theme_value": current_theme_value,
            "current_diary_voice": current_diary_voice,
            "members": members, "admin_count": admin_count,
            "restore_success": request.query_params.get("restore_success"),
            "restore_error": request.query_params.get("restore_error"),
            "current_site_title": current_site_title,
            "logins": logins, "saved": False,
        },
    )


@app.post("/settings/site-title")
def settings_site_title(request: Request, site_title: str = Form("")):
    user = require_login(request)
    if not user or not user["is_admin"]:
        return RedirectResponse(url="/")
    site_title = site_title.strip()
    if site_title:
        database.set_setting("SITE_TITLE", site_title)
    return RedirectResponse(url="/settings", status_code=303)


VALID_THEMES = {"dark_umber", "light_cream", "forest", "ocean"}


@app.post("/settings/theme")
def settings_theme(request: Request, theme: str = Form("")):
    user = require_login(request)
    if not user or not user["is_admin"]:
        return RedirectResponse(url="/")
    if theme in VALID_THEMES:
        database.set_setting("THEME", theme)
    return RedirectResponse(url="/settings#general", status_code=303)


@app.post("/settings/diary-voice")
def settings_diary_voice(request: Request, voice: str = Form("")):
    user = require_login(request)
    if not user or not user["is_admin"]:
        return RedirectResponse(url="/")
    if voice in ("guardian", "dog"):
        database.set_setting("DIARY_VOICE", voice)
    return RedirectResponse(url="/settings#general", status_code=303)


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


@app.post("/settings/signup-mode")
def settings_signup_mode(request: Request, enabled: str = Form("")):
    user = require_login(request)
    if not user or not user["is_admin"]:
        return RedirectResponse(url="/")
    database.set_setting("SIGNUP_ENABLED", "1" if enabled == "1" else "0")
    return RedirectResponse(url="/settings", status_code=303)


# ---------- 회원 관리 (관리자 전용) ----------

@app.post("/settings/members/{member_id}/toggle-admin")
def settings_toggle_admin(request: Request, member_id: int):
    user = require_login(request)
    if not user or not user["is_admin"]:
        return RedirectResponse(url="/")
    target = database.get_user_by_id(member_id)
    if not target:
        return RedirectResponse(url="/settings#members", status_code=303)
    if target["is_admin"] and database.count_admins() <= 1:
        # 마지막 남은 관리자는 해제할 수 없습니다.
        return RedirectResponse(url="/settings#members", status_code=303)
    database.set_user_admin(member_id, not target["is_admin"])
    return RedirectResponse(url="/settings#members", status_code=303)


@app.post("/settings/members/{member_id}/delete")
def settings_delete_member(request: Request, member_id: int):
    user = require_login(request)
    if not user or not user["is_admin"]:
        return RedirectResponse(url="/")
    target = database.get_user_by_id(member_id)
    if not target:
        return RedirectResponse(url="/settings#members", status_code=303)
    if target["is_admin"] and database.count_admins() <= 1:
        # 마지막 남은 관리자 계정은 삭제할 수 없습니다.
        return RedirectResponse(url="/settings#members", status_code=303)
    shutil.rmtree(UPLOAD_DIR / str(member_id), ignore_errors=True)
    database.delete_user(member_id)
    return RedirectResponse(url="/settings#members", status_code=303)


# ---------- 백업 및 복구 ----------

@app.get("/settings/backup/download")
def settings_backup_download(request: Request):
    user = require_login(request)
    if not user or not user["is_admin"]:
        return RedirectResponse(url="/")

    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    backup_filename = f"pet-diary-backup-{timestamp}.zip"
    backup_path = Path(tempfile.gettempdir()) / f"{uuid.uuid4().hex}-{backup_filename}"

    with zipfile.ZipFile(backup_path, "w", zipfile.ZIP_DEFLATED) as zf:
        db_path = BASE_DIR / "data" / "diary.db"
        if db_path.exists():
            zf.write(db_path, arcname="diary.db")
        for file_path in UPLOAD_DIR.rglob("*"):
            if file_path.is_file() and "_tmp" not in file_path.parts:
                zf.write(file_path, arcname=str(Path("uploads") / file_path.relative_to(UPLOAD_DIR)))

    cleanup = BackgroundTask(lambda: backup_path.unlink(missing_ok=True))
    return FileResponse(
        backup_path, filename=backup_filename, media_type="application/zip", background=cleanup
    )


@app.post("/settings/backup/restore")
async def settings_backup_restore(request: Request, backup_file: UploadFile = None):
    user = require_login(request)
    if not user or not user["is_admin"]:
        return RedirectResponse(url="/")

    if not backup_file or not backup_file.filename:
        return RedirectResponse(url="/settings?restore_error=1", status_code=303)

    tmp_zip_path = Path(tempfile.gettempdir()) / f"restore_{uuid.uuid4().hex}.zip"
    with tmp_zip_path.open("wb") as f:
        shutil.copyfileobj(backup_file.file, f)

    try:
        with zipfile.ZipFile(tmp_zip_path) as zf:
            names = zf.namelist()
            if "diary.db" not in names:
                return RedirectResponse(url="/settings?restore_error=1", status_code=303)

            data_dir = BASE_DIR / "data"
            safety_timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
            safety_dir = BASE_DIR / f"data_before_restore_{safety_timestamp}"
            shutil.copytree(data_dir, safety_dir)

            # DB 교체
            with zf.open("diary.db") as src, open(data_dir / "diary.db", "wb") as dst:
                shutil.copyfileobj(src, dst)

            # uploads 폴더 교체
            uploads_dir = data_dir / "uploads"
            shutil.rmtree(uploads_dir, ignore_errors=True)
            uploads_dir.mkdir(parents=True, exist_ok=True)
            for name in names:
                if name.startswith("uploads/") and not name.endswith("/"):
                    target = data_dir / name
                    target.parent.mkdir(parents=True, exist_ok=True)
                    with zf.open(name) as src, open(target, "wb") as dst:
                        shutil.copyfileobj(src, dst)
    except (zipfile.BadZipFile, OSError):
        return RedirectResponse(url="/settings?restore_error=1", status_code=303)
    finally:
        tmp_zip_path.unlink(missing_ok=True)

    return RedirectResponse(url="/settings?restore_success=1", status_code=303)


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
        "home.html",
        {
            "request": request, "dogs": dogs, "user": None, "guest": True,
            "latest_notice": database.get_latest_notice(),
        },
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
    entry_photos = {e["id"]: database.get_entry_photos(e["id"]) for e in entries}
    entry_reactions = {e["id"]: database.get_reaction_summary(e["id"]) for e in entries}
    entry_comments = {e["id"]: database.list_comments(e["id"]) for e in entries}
    return templates.TemplateResponse(
        "album.html",
        {
            "request": request, "user": None, "dog": dog, "entries": entries,
            "entry_photos": entry_photos, "entry_reactions": entry_reactions,
            "my_reactions": {}, "entry_comments": entry_comments,
            "uploaded": 0, "failed": 0, "guest": True,
        },
    )


# ---------- 공지사항 ----------

def _can_view_notices(request: Request):
    """로그인 사용자이거나, 게스트 모드가 켜져있으면 True."""
    user = auth.get_current_user(request)
    if user:
        return user, False
    if settings.get_bool("GUEST_MODE_ENABLED"):
        return None, True
    return None, None  # 둘 다 아니면 접근 불가


@app.get("/notices")
def notices_list(request: Request):
    user, guest = _can_view_notices(request)
    if user is None and not guest:
        return RedirectResponse(url="/login")
    if user:
        database.update_notices_last_seen(user["id"])
    notices = database.list_notices()
    new_cutoff = (datetime.now() - timedelta(days=3)).strftime("%Y-%m-%d %H:%M:%S")
    return templates.TemplateResponse(
        "notices.html",
        {"request": request, "user": user, "guest": guest, "notices": notices, "new_cutoff": new_cutoff},
    )


@app.get("/notices/new")
def notice_new_form(request: Request):
    user = require_login(request)
    if not user or not user["is_admin"]:
        return RedirectResponse(url="/notices")
    return templates.TemplateResponse(
        "notice_form.html", {"request": request, "user": user, "notice": None, "error": None}
    )


@app.post("/notices/new")
def notice_new_submit(request: Request, title: str = Form(...), content: str = Form(...)):
    user = require_login(request)
    if not user or not user["is_admin"]:
        return RedirectResponse(url="/notices")
    title = title.strip()
    content = content.strip()
    if not title or not content:
        return templates.TemplateResponse(
            "notice_form.html",
            {"request": request, "user": user, "notice": None, "error": "제목과 내용을 모두 입력해주세요."},
        )
    notice_id = database.create_notice(title, content, user["username"])
    return RedirectResponse(url=f"/notices/{notice_id}", status_code=303)


@app.get("/notices/{notice_id}")
def notice_detail(request: Request, notice_id: int):
    user, guest = _can_view_notices(request)
    if user is None and not guest:
        return RedirectResponse(url="/login")
    notice = database.get_notice(notice_id)
    if not notice:
        return RedirectResponse(url="/notices", status_code=303)
    return templates.TemplateResponse(
        "notice_detail.html", {"request": request, "user": user, "guest": guest, "notice": notice}
    )


@app.get("/notices/{notice_id}/edit")
def notice_edit_form(request: Request, notice_id: int):
    user = require_login(request)
    if not user or not user["is_admin"]:
        return RedirectResponse(url="/notices")
    notice = database.get_notice(notice_id)
    if not notice:
        return RedirectResponse(url="/notices", status_code=303)
    return templates.TemplateResponse(
        "notice_form.html", {"request": request, "user": user, "notice": notice, "error": None}
    )


@app.post("/notices/{notice_id}/edit")
def notice_edit_submit(request: Request, notice_id: int, title: str = Form(...), content: str = Form(...)):
    user = require_login(request)
    if not user or not user["is_admin"]:
        return RedirectResponse(url="/notices")
    notice = database.get_notice(notice_id)
    if not notice:
        return RedirectResponse(url="/notices", status_code=303)
    title = title.strip()
    content = content.strip()
    if not title or not content:
        return templates.TemplateResponse(
            "notice_form.html",
            {"request": request, "user": user, "notice": notice, "error": "제목과 내용을 모두 입력해주세요."},
        )
    database.update_notice(notice_id, title, content)
    return RedirectResponse(url=f"/notices/{notice_id}", status_code=303)


@app.post("/notices/{notice_id}/delete")
def notice_delete(request: Request, notice_id: int):
    user = require_login(request)
    if not user or not user["is_admin"]:
        return RedirectResponse(url="/notices")
    database.delete_notice(notice_id)
    return RedirectResponse(url="/notices", status_code=303)


# ---------- 쪽지 ----------

@app.get("/messages")
def messages_inbox(request: Request):
    user = require_login(request)
    if not user:
        return RedirectResponse(url="/login")
    inbox = database.list_inbox(user["id"])
    for m in inbox:
        if not m["is_read"]:
            database.mark_message_read(m["id"])
    return templates.TemplateResponse(
        "messages.html", {"request": request, "user": user, "messages": inbox, "box": "inbox"}
    )


@app.get("/messages/sent")
def messages_sent(request: Request):
    user = require_login(request)
    if not user:
        return RedirectResponse(url="/login")
    sent = database.list_sent(user["id"])
    return templates.TemplateResponse(
        "messages.html", {"request": request, "user": user, "messages": sent, "box": "sent"}
    )


@app.get("/messages/new")
def message_new_form(request: Request):
    user = require_login(request)
    if not user:
        return RedirectResponse(url="/login")
    recipients = database.list_other_users(user["id"])
    to = request.query_params.get("to", "")
    return templates.TemplateResponse(
        "message_new.html",
        {"request": request, "user": user, "recipients": recipients, "error": None, "preselect": to},
    )


@app.post("/messages/new")
def message_new_submit(request: Request, recipient_id: int = Form(...), content: str = Form(...)):
    user = require_login(request)
    if not user:
        return RedirectResponse(url="/login")
    recipient = database.get_user_by_id(recipient_id)
    content = content.strip()[:1000]
    if not recipient or not content:
        recipients = database.list_other_users(user["id"])
        return templates.TemplateResponse(
            "message_new.html",
            {
                "request": request, "user": user, "recipients": recipients,
                "error": "받는 사람과 내용을 모두 입력해주세요.", "preselect": "",
            },
        )
    database.send_message(user["id"], user["username"], recipient["id"], recipient["username"], content)
    return RedirectResponse(url="/messages/sent", status_code=303)


@app.post("/messages/{message_id}/delete")
def message_delete(request: Request, message_id: int):
    user = require_login(request)
    if not user:
        return RedirectResponse(url="/login")
    message = database.get_message(message_id)
    if not message:
        return RedirectResponse(url="/messages", status_code=303)
    if message["sender_id"] != user["id"] and message["recipient_id"] != user["id"]:
        return RedirectResponse(url="/messages", status_code=303)
    database.delete_message(message_id)
    back = "sent" if message["sender_id"] == user["id"] else "inbox"
    return RedirectResponse(url=f"/messages{'/sent' if back == 'sent' else ''}", status_code=303)


# ---------- 가족 초대 ----------

@app.get("/family")
def family_page(request: Request):
    user = require_login(request)
    if not user:
        return RedirectResponse(url="/login")
    token = database.get_or_create_invite_token(user["id"])
    members = database.list_family_members(user["id"])
    invite_url = str(request.base_url).rstrip("/") + f"/family/join/{token}"
    return templates.TemplateResponse(
        "family.html",
        {"request": request, "user": user, "members": members, "invite_url": invite_url, "joined": request.query_params.get("joined")},
    )


@app.post("/family/invite/regenerate")
def family_regenerate_invite(request: Request):
    user = require_login(request)
    if not user:
        return RedirectResponse(url="/login")
    database.regenerate_invite_token(user["id"])
    return RedirectResponse(url="/family", status_code=303)


@app.get("/family/join/{token}")
def family_join(request: Request, token: str):
    user = auth.get_current_user(request)
    if not user:
        request.session["post_login_redirect"] = f"/family/join/{token}"
        return RedirectResponse(url="/login")
    inviter = database.get_user_by_invite_token(token)
    if not inviter:
        return RedirectResponse(url="/family", status_code=303)
    if inviter["id"] == user["id"]:
        return RedirectResponse(url="/family", status_code=303)
    database.add_family_link(inviter["id"], user["id"])
    return RedirectResponse(url="/family?joined=1", status_code=303)


@app.post("/family/{member_id}/remove")
def family_remove(request: Request, member_id: int):
    user = require_login(request)
    if not user:
        return RedirectResponse(url="/login")
    database.remove_family_link(user["id"], member_id)
    return RedirectResponse(url="/family", status_code=303)


# ---------- 홈 ----------

@app.get("/")
def home(request: Request):
    user = require_login(request)
    if not user:
        return RedirectResponse(url="/login")
    dogs = database.list_dogs(user["id"])
    family_dogs = database.list_family_dogs(user["id"])
    dog_has_new_comment = {}
    if database.get_comment_notifications_enabled(user["id"]):
        for d in dogs:
            latest = database.get_latest_comment_at(d["id"])
            last_seen = d["comments_last_seen_at"]
            dog_has_new_comment[d["id"]] = bool(latest) and (not last_seen or latest > last_seen)
    return templates.TemplateResponse(
        "home.html",
        {
            "request": request, "dogs": dogs, "family_dogs": family_dogs, "user": user,
            "latest_notice": database.get_latest_notice(),
            "dog_has_new_comment": dog_has_new_comment,
        },
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
    bundle_photos: str = Form(""),
    media_mode: str = Form("photo"),
    photos: list[UploadFile] = None,
    video: UploadFile = None,
):
    user = require_login(request)
    if not user:
        return RedirectResponse(url="/login")

    dog_name = dog_name.strip()
    dogs = database.list_dogs(user["id"])

    if media_mode == "video":
        return await _upload_video(request, user, dogs, dog_name, ai_provider, video)

    auto_identify = auto_identify == "1"
    bundle_photos = bundle_photos == "1"
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

    weather_icon = weather.get_current_weather_emoji()

    # 1) 사진 파일들을 먼저 전부 저장합니다.
    saved = []  # [(절대경로, DB에 저장할 상대경로), ...]
    for index, photo in enumerate(photos):
        ext = Path(photo.filename or "photo.jpg").suffix or ".jpg"
        saved_name = f"{uuid.uuid4().hex}{ext}"
        saved_path = user_folder / saved_name

        if index == 0 and identified_tmp_path is not None:
            shutil.move(str(identified_tmp_path), str(saved_path))
        else:
            with saved_path.open("wb") as f:
                shutil.copyfileobj(photo.file, f)

        relative_path = f"{user['id']}/{dog_name}/{saved_name}"
        saved.append((saved_path, relative_path))

    dog_id = None
    success_count = 0
    fail_count = 0

    if bundle_photos and len(saved) > 1:
        # 2-A) 여러 장을 하나의 일기로 묶어서 AI에게 한 번에 보여줍니다.
        abs_paths = [str(s[0]) for s in saved]
        try:
            breed_guess, diary_text = ai_providers.generate_diary_entry_multi(abs_paths, dog_name, ai_provider)
            success_count = len(saved)
        except Exception as exc:  # noqa: BLE001
            breed_guess, diary_text = None, f"(AI 일기 생성 실패: {exc})"
            fail_count = len(saved)

        dog_id = database.get_or_create_dog(user["id"], dog_name, breed_guess)
        relative_paths = [s[1] for s in saved]
        database.add_entry(dog_id, relative_paths, diary_text, ai_provider, weather_icon)
    else:
        # 2-B) 사진마다 각각 별도의 일기를 만듭니다.
        for saved_path, relative_path in saved:
            try:
                breed_guess, diary_text = ai_providers.generate_diary_entry(str(saved_path), dog_name, ai_provider)
                success_count += 1
            except Exception as exc:  # noqa: BLE001
                breed_guess, diary_text = None, f"(AI 일기 생성 실패: {exc})"
                fail_count += 1

            dog_id = database.get_or_create_dog(user["id"], dog_name, breed_guess)
            database.add_entry(dog_id, [relative_path], diary_text, ai_provider, weather_icon)

    if dog_id is None:
        return RedirectResponse(url="/upload", status_code=303)

    redirect_url = f"/dog/{dog_id}?uploaded={success_count}&failed={fail_count}"
    return RedirectResponse(url=redirect_url, status_code=303)


async def _upload_video(request: Request, user, dogs, dog_name: str, ai_provider: str, video: UploadFile | None):
    """짧은 동영상(30초 이내) 한 개를 업로드해서 일기 하나를 만듭니다."""
    MAX_VIDEO_SECONDS = 30
    MAX_VIDEO_MB = 40

    if not video or not video.filename:
        return templates.TemplateResponse(
            "upload.html",
            {"request": request, "user": user, "dogs": dogs, "error": "동영상 파일을 선택해주세요."},
        )
    if not dog_name:
        return templates.TemplateResponse(
            "upload.html",
            {"request": request, "user": user, "dogs": dogs, "error": "반려견 이름을 입력해주세요."},
        )

    tmp_dir = UPLOAD_DIR / str(user["id"]) / "_tmp"
    tmp_dir.mkdir(parents=True, exist_ok=True)
    ext = Path(video.filename or "video.mp4").suffix or ".mp4"
    tmp_video_path = tmp_dir / f"{uuid.uuid4().hex}{ext}"
    with tmp_video_path.open("wb") as f:
        shutil.copyfileobj(video.file, f)

    size_mb = tmp_video_path.stat().st_size / (1024 * 1024)
    if size_mb > MAX_VIDEO_MB:
        tmp_video_path.unlink(missing_ok=True)
        return templates.TemplateResponse(
            "upload.html",
            {
                "request": request, "user": user, "dogs": dogs,
                "error": f"동영상 용량이 너무 커요 ({size_mb:.0f}MB). {MAX_VIDEO_MB}MB 이내로 올려주세요.",
            },
        )

    duration = video_utils.get_duration_seconds(str(tmp_video_path))
    if duration is not None and duration > MAX_VIDEO_SECONDS:
        tmp_video_path.unlink(missing_ok=True)
        return templates.TemplateResponse(
            "upload.html",
            {
                "request": request, "user": user, "dogs": dogs,
                "error": f"{MAX_VIDEO_SECONDS}초 이내 동영상만 업로드할 수 있어요. (지금 영상은 약 {duration:.0f}초예요)",
            },
        )

    weather_icon = weather.get_current_weather_emoji()

    if ai_provider == "gemini":
        try:
            breed_guess, diary_text = ai_providers.generate_diary_entry_video(str(tmp_video_path), dog_name, ai_provider)
            success_count, fail_count = 1, 0
        except Exception as exc:  # noqa: BLE001
            breed_guess, diary_text = None, f"(AI 일기 생성 실패: {exc})"
            success_count, fail_count = 0, 1
    else:
        frame_path = tmp_dir / f"{uuid.uuid4().hex}_frame.jpg"
        frame_ok = video_utils.extract_thumbnail_frame(str(tmp_video_path), str(frame_path))
        if frame_ok:
            try:
                breed_guess, diary_text = ai_providers.generate_diary_entry(str(frame_path), dog_name, ai_provider)
                success_count, fail_count = 1, 0
            except Exception as exc:  # noqa: BLE001
                breed_guess, diary_text = None, f"(AI 일기 생성 실패: {exc})"
                success_count, fail_count = 0, 1
            frame_path.unlink(missing_ok=True)
        else:
            breed_guess, diary_text = None, (
                "(동영상의 대표 장면을 추출하지 못해 일기를 쓰지 못했어요. "
                "Gemini를 선택하면 영상을 직접 분석할 수 있어요.)"
            )
            success_count, fail_count = 0, 1

    user_folder = UPLOAD_DIR / str(user["id"]) / dog_name
    user_folder.mkdir(parents=True, exist_ok=True)
    saved_name = f"{uuid.uuid4().hex}{ext}"
    saved_path = user_folder / saved_name
    shutil.move(str(tmp_video_path), str(saved_path))
    relative_path = f"{user['id']}/{dog_name}/{saved_name}"

    dog_id = database.get_or_create_dog(user["id"], dog_name, breed_guess)
    database.add_entry(dog_id, [relative_path], diary_text, ai_provider, weather_icon, media_type="video")

    return RedirectResponse(url=f"/dog/{dog_id}?uploaded={success_count}&failed={fail_count}", status_code=303)


# ---------- 반려견 상세 / 수정 / 삭제 ----------

@app.get("/dog/{dog_id}")
def dog_album(request: Request, dog_id: int, uploaded: int = 0, failed: int = 0):
    user = require_login(request)
    if not user:
        return RedirectResponse(url="/login")
    dog = database.get_dog_for_viewing(user["id"], dog_id)
    is_owner = bool(dog) and dog["user_id"] == user["id"]
    dog_owner_username = None
    if dog and not is_owner:
        owner = database.get_user_by_id(dog["user_id"])
        dog_owner_username = owner["username"] if owner else None
    if dog and is_owner:
        database.update_dog_comments_seen(dog_id)
    entries = database.list_entries_for_dog(dog_id) if dog else []
    entry_photos = {e["id"]: database.get_entry_photos(e["id"]) for e in entries}
    entry_reactions = {e["id"]: database.get_reaction_summary(e["id"]) for e in entries}
    my_reactions = {e["id"]: database.get_user_reaction(e["id"], user["id"]) for e in entries}
    entry_comments = {e["id"]: database.list_comments(e["id"]) for e in entries}
    return templates.TemplateResponse(
        "album.html",
        {
            "request": request,
            "user": user,
            "dog": dog,
            "is_owner": is_owner,
            "dog_owner_username": dog_owner_username,
            "entries": entries,
            "entry_photos": entry_photos,
            "entry_reactions": entry_reactions,
            "my_reactions": my_reactions,
            "entry_comments": entry_comments,
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
async def dog_edit_submit(
    request: Request,
    dog_id: int,
    name: str = Form(...),
    breed_guess: str = Form(""),
    profile_photo: UploadFile = None,
    remove_profile_photo: str = Form(""),
):
    user = require_login(request)
    if not user:
        return RedirectResponse(url="/login")
    name = name.strip()
    dog = database.get_dog(user["id"], dog_id)
    if not dog:
        return RedirectResponse(url="/", status_code=303)
    if not name:
        return templates.TemplateResponse(
            "dog_edit.html", {"request": request, "user": user, "dog": dog, "error": "이름을 입력해주세요."}
        )
    database.update_dog(user["id"], dog_id, name, breed_guess.strip() or None)

    if remove_profile_photo == "1":
        if dog["profile_photo"]:
            (UPLOAD_DIR / dog["profile_photo"]).unlink(missing_ok=True)
        database.set_dog_profile_photo(user["id"], dog_id, None)
    elif profile_photo is not None and profile_photo.filename:
        user_folder = UPLOAD_DIR / str(user["id"]) / name
        user_folder.mkdir(parents=True, exist_ok=True)
        ext = Path(profile_photo.filename).suffix or ".jpg"
        saved_name = f"profile_{uuid.uuid4().hex}{ext}"
        saved_path = user_folder / saved_name
        with saved_path.open("wb") as f:
            shutil.copyfileobj(profile_photo.file, f)
        if dog["profile_photo"]:
            (UPLOAD_DIR / dog["profile_photo"]).unlink(missing_ok=True)
        relative_path = f"{user['id']}/{name}/{saved_name}"
        database.set_dog_profile_photo(user["id"], dog_id, relative_path)

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


@app.get("/entry/{entry_id}/download")
def entry_download(request: Request, entry_id: int):
    user = require_login(request)
    if not user:
        return RedirectResponse(url="/login")
    entry = database.get_entry(entry_id)
    if not entry:
        return RedirectResponse(url="/", status_code=303)
    dog = database.get_dog_for_viewing(user["id"], entry["dog_id"])
    if not dog:
        return RedirectResponse(url="/", status_code=303)

    media = database.get_entry_photos(entry_id)
    if not media:
        media = [{"path": entry["photo_path"], "media_type": "photo"}]

    tmp_frame_path = None
    if media[0]["media_type"] == "video":
        # 동영상 일기는 대표 장면 한 컷만 추출해서 사용합니다.
        video_abs_path = UPLOAD_DIR / media[0]["path"]
        tmp_frame_path = Path(tempfile.gettempdir()) / f"polaroid_frame_{uuid.uuid4().hex}.jpg"
        if video_utils.extract_thumbnail_frame(str(video_abs_path), str(tmp_frame_path)):
            photo_paths = [tmp_frame_path]
        else:
            photo_paths = [video_abs_path]
    else:
        photo_paths = [UPLOAD_DIR / m["path"] for m in media if m["media_type"] != "video"]
        if not photo_paths:
            photo_paths = [UPLOAD_DIR / media[0]["path"]]

    output_path = Path(tempfile.gettempdir()) / f"polaroid_{uuid.uuid4().hex}.jpg"
    try:
        polaroid.create_polaroid(
            photo_paths, dog["name"], entry["created_at"][:10], entry["diary_text"] or "", output_path
        )
    finally:
        if tmp_frame_path:
            tmp_frame_path.unlink(missing_ok=True)

    cleanup = BackgroundTask(lambda: output_path.unlink(missing_ok=True))
    filename = f"{dog['name']}_{entry['created_at'][:10]}.jpg"
    return FileResponse(output_path, filename=filename, media_type="image/jpeg", background=cleanup)


@app.post("/entry/{entry_id}/delete")
def entry_delete(request: Request, entry_id: int):
    user = require_login(request)
    if not user:
        return RedirectResponse(url="/login")
    entry = database.get_entry(entry_id)
    if entry:
        dog = database.get_dog(user["id"], entry["dog_id"])
        if dog:
            for media in database.get_entry_photos(entry_id):
                (UPLOAD_DIR / media["path"]).unlink(missing_ok=True)
            database.delete_entry(entry_id)
            return RedirectResponse(url=f"/dog/{dog['id']}", status_code=303)
    return RedirectResponse(url="/", status_code=303)


# ---------- 일기 안 사진/동영상 관리 (추가/개별 삭제) ----------

@app.get("/entry/{entry_id}/edit")
def entry_edit_form(request: Request, entry_id: int):
    user = require_login(request)
    if not user:
        return RedirectResponse(url="/login")
    entry = database.get_entry(entry_id)
    if not entry:
        return RedirectResponse(url="/", status_code=303)
    dog = database.get_dog(user["id"], entry["dog_id"])
    if not dog:
        return RedirectResponse(url="/", status_code=303)
    media = database.get_entry_photos(entry_id)
    entry_media_type = media[0]["media_type"] if media else "photo"
    return templates.TemplateResponse(
        "entry_edit.html",
        {
            "request": request, "user": user, "dog": dog, "entry": entry,
            "media": media, "entry_media_type": entry_media_type, "error": None,
        },
    )


@app.post("/entry/{entry_id}/media/add")
async def entry_media_add(request: Request, entry_id: int, photos: list[UploadFile] = None):
    user = require_login(request)
    if not user:
        return RedirectResponse(url="/login")
    entry = database.get_entry(entry_id)
    if not entry:
        return RedirectResponse(url="/", status_code=303)
    dog = database.get_dog(user["id"], entry["dog_id"])
    if not dog:
        return RedirectResponse(url="/", status_code=303)

    photos = [p for p in (photos or []) if p and p.filename]
    if photos:
        user_folder = UPLOAD_DIR / str(user["id"]) / dog["name"]
        user_folder.mkdir(parents=True, exist_ok=True)
        new_paths = []
        for photo in photos:
            ext = Path(photo.filename or "photo.jpg").suffix or ".jpg"
            saved_name = f"{uuid.uuid4().hex}{ext}"
            saved_path = user_folder / saved_name
            with saved_path.open("wb") as f:
                shutil.copyfileobj(photo.file, f)
            new_paths.append(f"{user['id']}/{dog['name']}/{saved_name}")
        database.add_entry_photos(entry_id, new_paths, media_type="photo")

    return RedirectResponse(url=f"/entry/{entry_id}/edit", status_code=303)


@app.post("/entry/{entry_id}/media/{entry_photo_id}/delete")
def entry_media_delete(request: Request, entry_id: int, entry_photo_id: int):
    user = require_login(request)
    if not user:
        return RedirectResponse(url="/login")
    entry = database.get_entry(entry_id)
    if not entry:
        return RedirectResponse(url="/", status_code=303)
    dog = database.get_dog(user["id"], entry["dog_id"])
    if not dog:
        return RedirectResponse(url="/", status_code=303)

    total = database.count_entry_photos(entry_id)
    if total <= 1:
        # 마지막 하나 남은 사진/동영상이면 일기 전체를 삭제합니다.
        for media in database.get_entry_photos(entry_id):
            (UPLOAD_DIR / media["path"]).unlink(missing_ok=True)
        database.delete_entry(entry_id)
        return RedirectResponse(url=f"/dog/{dog['id']}", status_code=303)

    row = database.get_entry_photo_row(entry_photo_id)
    if row and row["entry_id"] == entry_id:
        (UPLOAD_DIR / row["photo_path"]).unlink(missing_ok=True)
        database.delete_entry_photo(entry_photo_id)
        database.resync_entry_cover(entry_id)

    return RedirectResponse(url=f"/entry/{entry_id}/edit", status_code=303)


# ---------- 반응(이모지) / 댓글 ----------

@app.post("/entry/{entry_id}/react")
def entry_react(request: Request, entry_id: int, emoji: str = Form(...)):
    user = auth.get_current_user(request)
    if not user:
        return JSONResponse({"error": "login_required"}, status_code=401)
    entry = database.get_entry(entry_id)
    if not entry or emoji not in REACTION_EMOJIS:
        return JSONResponse({"error": "invalid"}, status_code=400)
    dog = database.get_dog_for_viewing(user["id"], entry["dog_id"])
    if not dog:
        return JSONResponse({"error": "forbidden"}, status_code=403)
    database.toggle_reaction(entry_id, user["id"], emoji)
    return JSONResponse({
        "summary": database.get_reaction_summary(entry_id),
        "my_reaction": database.get_user_reaction(entry_id, user["id"]),
    })


@app.post("/entry/{entry_id}/comment")
def entry_comment_add(request: Request, entry_id: int, content: str = Form(...)):
    user = auth.get_current_user(request)
    if not user:
        return JSONResponse({"error": "login_required"}, status_code=401)
    entry = database.get_entry(entry_id)
    if not entry:
        return JSONResponse({"error": "not_found"}, status_code=404)
    dog = database.get_dog_for_viewing(user["id"], entry["dog_id"])
    if not dog:
        return JSONResponse({"error": "forbidden"}, status_code=403)
    content = content.strip()[:500]
    if not content:
        return JSONResponse({"error": "empty"}, status_code=400)
    comment_id = database.add_comment(entry_id, user["id"], user["username"], content)
    return JSONResponse({"id": comment_id, "username": user["username"], "content": content})


@app.post("/comment/{comment_id}/delete")
def comment_delete(request: Request, comment_id: int):
    user = auth.get_current_user(request)
    if not user:
        return JSONResponse({"error": "login_required"}, status_code=401)
    comment = database.get_comment(comment_id)
    if not comment:
        return JSONResponse({"ok": True})
    if comment["user_id"] != user["id"] and not user["is_admin"]:
        return JSONResponse({"error": "forbidden"}, status_code=403)
    database.delete_comment(comment_id)
    return JSONResponse({"ok": True})


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
