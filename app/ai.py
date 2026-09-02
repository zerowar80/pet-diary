import base64
import mimetypes
import os

from anthropic import Anthropic

_client: Anthropic | None = None


def get_client() -> Anthropic:
    global _client
    if _client is None:
        api_key = os.environ.get("ANTHROPIC_API_KEY")
        if not api_key:
            raise RuntimeError(
                "ANTHROPIC_API_KEY가 설정되지 않았습니다. .env 파일을 확인하세요."
            )
        _client = Anthropic(api_key=api_key)
    return _client


def _image_block(path: str) -> dict:
    media_type = mimetypes.guess_type(path)[0] or "image/jpeg"
    with open(path, "rb") as f:
        data = base64.standard_b64encode(f.read()).decode("utf-8")
    return {
        "type": "image",
        "source": {"type": "base64", "media_type": media_type, "data": data},
    }


def generate_diary_entry(photo_path: str, dog_name: str) -> tuple[str, str]:
    """사진을 분석해 (견종 추정, 일기 텍스트) 를 반환합니다."""
    client = get_client()
    prompt = (
        f"이 사진은 반려견 '{dog_name}'의 사진입니다. "
        "사진을 보고 다음 두 가지를 작성해주세요.\n"
        "1. 견종 또는 견종 특징에 대한 아주 짧은 추정 (예: '말티푸로 추정', 알 수 없으면 '믹스견').\n"
        "2. 사진 속 상황을 바탕으로 반려견의 하루를 상상한 다정하고 짧은 일기 (2~3문장, 보호자 시점, 반말이 아닌 부드러운 존댓말).\n\n"
        "아래 형식을 정확히 지켜서 답변하세요. 다른 설명은 절대 추가하지 마세요.\n"
        "견종: <내용>\n"
        "일기: <내용>"
    )
    response = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=400,
        messages=[
            {
                "role": "user",
                "content": [_image_block(photo_path), {"type": "text", "text": prompt}],
            }
        ],
    )
    text = "".join(block.text for block in response.content if block.type == "text")

    breed_guess = "믹스견"
    diary = text.strip()
    for line in text.splitlines():
        line = line.strip()
        if line.startswith("견종:"):
            breed_guess = line.replace("견종:", "").strip()
        elif line.startswith("일기:"):
            diary = line.replace("일기:", "").strip()

    return breed_guess, diary
