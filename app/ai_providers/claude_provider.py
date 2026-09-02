import os

from anthropic import Anthropic

from .common import build_prompt, encode_image, parse_response


def generate(photo_path: str, dog_name: str) -> tuple[str, str]:
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        raise RuntimeError("ANTHROPIC_API_KEY가 .env에 설정되어 있지 않습니다.")

    model = os.environ.get("CLAUDE_MODEL", "claude-sonnet-4-6")
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
                    {"type": "text", "text": build_prompt(dog_name)},
                ],
            }
        ],
    )
    text = "".join(block.text for block in response.content if block.type == "text")
    return parse_response(text)
