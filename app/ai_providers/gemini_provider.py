import google.generativeai as genai
from PIL import Image

from .. import settings
from .common import build_prompt, parse_response


def generate(photo_path: str, dog_name: str) -> tuple[str, str]:
    api_key = settings.get("GOOGLE_API_KEY")
    if not api_key:
        raise RuntimeError("GOOGLE_API_KEY가 설정되어 있지 않습니다. 설정 화면이나 .env에서 입력해주세요.")

    model_name = settings.get("GEMINI_MODEL", "gemini-flash-latest")
    genai.configure(api_key=api_key)
    model = genai.GenerativeModel(model_name)

    image = Image.open(photo_path)
    response = model.generate_content([build_prompt(dog_name), image])
    text = response.text or ""
    return parse_response(text)


def generate_text(prompt: str, image_paths: list[str] | None = None) -> str:
    """이미지 0~여러 장 + 텍스트 프롬프트로 자유 형식 텍스트를 생성합니다."""
    api_key = settings.get("GOOGLE_API_KEY")
    if not api_key:
        raise RuntimeError("GOOGLE_API_KEY가 설정되어 있지 않습니다. 설정 화면이나 .env에서 입력해주세요.")

    model_name = settings.get("GEMINI_MODEL", "gemini-flash-latest")
    genai.configure(api_key=api_key)
    model = genai.GenerativeModel(model_name)

    parts = [Image.open(path) for path in (image_paths or [])]
    parts.append(prompt)

    response = model.generate_content(parts)
    return (response.text or "").strip()
