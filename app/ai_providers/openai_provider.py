from openai import OpenAI

from .. import settings
from .common import build_prompt, encode_image, parse_response


def generate(photo_path: str, dog_name: str) -> tuple[str, str]:
    api_key = settings.get("OPENAI_API_KEY")
    if not api_key:
        raise RuntimeError("OPENAI_API_KEY가 설정되어 있지 않습니다. 설정 화면이나 .env에서 입력해주세요.")

    model = settings.get("OPENAI_MODEL", "gpt-4o")
    client = OpenAI(api_key=api_key)
    data, media_type = encode_image(photo_path)

    response = client.chat.completions.create(
        model=model,
        max_tokens=400,
        messages=[
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": build_prompt(dog_name)},
                    {
                        "type": "image_url",
                        "image_url": {"url": f"data:{media_type};base64,{data}"},
                    },
                ],
            }
        ],
    )
    text = response.choices[0].message.content or ""
    return parse_response(text)


def generate_text(prompt: str, image_paths: list[str] | None = None) -> str:
    """이미지 0~여러 장 + 텍스트 프롬프트로 자유 형식 텍스트를 생성합니다."""
    api_key = settings.get("OPENAI_API_KEY")
    if not api_key:
        raise RuntimeError("OPENAI_API_KEY가 설정되어 있지 않습니다. 설정 화면이나 .env에서 입력해주세요.")

    model = settings.get("OPENAI_MODEL", "gpt-4o")
    client = OpenAI(api_key=api_key)

    content = [{"type": "text", "text": prompt}]
    for path in image_paths or []:
        data, media_type = encode_image(path)
        content.append({"type": "image_url", "image_url": {"url": f"data:{media_type};base64,{data}"}})

    response = client.chat.completions.create(
        model=model,
        max_tokens=600,
        messages=[{"role": "user", "content": content}],
    )
    return (response.choices[0].message.content or "").strip()
