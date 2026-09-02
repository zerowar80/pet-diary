import os

import google.generativeai as genai
from PIL import Image

from .common import build_prompt, parse_response


def generate(photo_path: str, dog_name: str) -> tuple[str, str]:
    api_key = os.environ.get("GOOGLE_API_KEY")
    if not api_key:
        raise RuntimeError("GOOGLE_API_KEY가 .env에 설정되어 있지 않습니다.")

    model_name = os.environ.get("GEMINI_MODEL", "gemini-2.0-flash")
    genai.configure(api_key=api_key)
    model = genai.GenerativeModel(model_name)

    image = Image.open(photo_path)
    response = model.generate_content([build_prompt(dog_name), image])
    text = response.text or ""
    return parse_response(text)
