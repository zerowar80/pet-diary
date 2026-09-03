from anthropic import Anthropic

from .. import settings
from .common import build_prompt, encode_image, parse_response


def generate(photo_path: str, dog_name: str) -> tuple[str, str]:
    api_key = settings.get("ANTHROPIC_API_KEY")
    if not api_key:
        raise RuntimeError("ANTHROPIC_API_KEY가 설정되어 있지 않습니다. 설정 화면이나 .env에서 입력해주세요.")

    model = settings.get("CLAUDE_MODEL", "claude-sonnet-4-6")
    client = Anthropic(api_key=api_key)
    data, media_type = encode_image(photo_path)

    response = client.messages.create(
        model=model,
        max_tokens=400,
        messages=[
            {
                "role": "user",
                "content": [
                    {
                        "type": "image",
                        "source": {"type": "base64", "media_type": media_type, "data": data},
                    },
                    {"type": "text", "text": build_prompt(dog_name, settings.get("DIARY_VOICE", "guardian"))},
                ],
            }
        ],
    )
    text = "".join(block.text for block in response.content if block.type == "text")
    return parse_response(text)


def generate_text(prompt: str, image_paths: list[str] | None = None) -> str:
    """이미지 0~여러 장 + 텍스트 프롬프트로 자유 형식 텍스트를 생성합니다."""
    api_key = settings.get("ANTHROPIC_API_KEY")
    if not api_key:
        raise RuntimeError("ANTHROPIC_API_KEY가 설정되어 있지 않습니다. 설정 화면이나 .env에서 입력해주세요.")

    model = settings.get("CLAUDE_MODEL", "claude-sonnet-4-6")
    client = Anthropic(api_key=api_key)

    content = []
    for path in image_paths or []:
        data, media_type = encode_image(path)
        content.append(
            {"type": "image", "source": {"type": "base64", "media_type": media_type, "data": data}}
        )
    content.append({"type": "text", "text": prompt})

    response = client.messages.create(
        model=model,
        max_tokens=600,
        messages=[{"role": "user", "content": content}],
    )
    return "".join(block.text for block in response.content if block.type == "text").strip()
