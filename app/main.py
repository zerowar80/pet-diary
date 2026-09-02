import shutil
import uuid
from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI, Form, Request, UploadFile
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from . import ai, database

load_dotenv()

BASE_DIR = Path(__file__).resolve().parent.parent
UPLOAD_DIR = BASE_DIR / "data" / "uploads"
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)

app = FastAPI(title="반려견 AI 사진 일기장")
templates = Jinja2Templates(directory=str(BASE_DIR / "app" / "templates"))

app.mount("/static", StaticFiles(directory=str(BASE_DIR / "app" / "static")), name="static")
app.mount("/photos", StaticFiles(directory=str(UPLOAD_DIR)), name="photos")


@app.on_event("startup")
def on_startup():
    database.init_db()


@app.get("/")
def home(request: Request):
    dogs = database.list_dogs()
    return templates.TemplateResponse("home.html", {"request": request, "dogs": dogs})


@app.get("/upload")
def upload_form(request: Request):
    return templates.TemplateResponse("upload.html", {"request": request, "error": None})


@app.post("/upload")
async def upload_photo(
    request: Request,
    dog_name: str = Form(...),
    photo: UploadFile = None,
):
    dog_name = dog_name.strip()
    if not dog_name or photo is None:
        return templates.TemplateResponse(
            "upload.html",
            {"request": request, "error": "반려견 이름과 사진을 모두 입력해주세요."},
        )

    dog_folder = UPLOAD_DIR / dog_name
    dog_folder.mkdir(parents=True, exist_ok=True)

    ext = Path(photo.filename or "photo.jpg").suffix or ".jpg"
    saved_name = f"{uuid.uuid4().hex}{ext}"
    saved_path = dog_folder / saved_name

    with saved_path.open("wb") as f:
        shutil.copyfileobj(photo.file, f)

    try:
        breed_guess, diary_text = ai.generate_diary_entry(str(saved_path), dog_name)
    except Exception as exc:  # noqa: BLE001
        breed_guess, diary_text = None, f"(AI 일기 생성 실패: {exc})"

    dog_id = database.get_or_create_dog(dog_name, breed_guess)
    relative_path = f"{dog_name}/{saved_name}"
    database.add_entry(dog_id, relative_path, diary_text)

    return RedirectResponse(url=f"/dog/{dog_name}", status_code=303)


@app.get("/dog/{dog_name}")
def dog_album(request: Request, dog_name: str):
    dog = database.get_dog_by_name(dog_name)
    entries = database.list_entries_for_dog(dog["id"]) if dog else []
    return templates.TemplateResponse(
        "album.html", {"request": request, "dog": dog, "entries": entries}
    )
