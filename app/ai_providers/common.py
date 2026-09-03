import base64
import mimetypes


def encode_image(path: str) -> tuple[str, str]:
    """(base64 데이터, media_type) 튜플을 반환합니다."""
    media_type = mimetypes.guess_type(path)[0] or "image/jpeg"
    with open(path, "rb") as f:
        data = base64.standard_b64encode(f.read()).decode("utf-8")
    return data, media_type


PROMPT_TEMPLATE = (
    "이 사진은 반려견 '{dog_name}'의 사진입니다. "
    "사진을 보고 다음 두 가지를 작성해주세요.\n"
    "1. 견종 또는 견종 특징에 대한 아주 짧은 추정 (예: '말티푸로 추정', 알 수 없으면 '믹스견').\n"
    "2. 사진 속 상황을 바탕으로 반려견의 하루를 상상한 다정하고 짧은 일기 (2~3문장, 보호자 시점, 부드러운 존댓말).\n\n"
    "아래 형식을 정확히 지켜서 답변하세요. 다른 설명은 절대 추가하지 마세요.\n"
    "견종: <내용>\n"
    "일기: <내용>"
)


def build_prompt(dog_name: str) -> str:
    return PROMPT_TEMPLATE.format(dog_name=dog_name)


MULTI_PROMPT_TEMPLATE = (
    "이 사진들은 모두 반려견 '{dog_name}'의 같은 날 찍은 사진 {count}장입니다. "
    "사진들을 종합해서 다음 두 가지를 작성해주세요.\n"
    "1. 견종 또는 견종 특징에 대한 아주 짧은 추정 (예: '말티푸로 추정', 알 수 없으면 '믹스견').\n"
    "2. 사진들 속 상황을 바탕으로 반려견의 하루를 상상한 다정하고 짧은 일기 (2~3문장, 보호자 시점, 부드러운 존댓말).\n\n"
    "아래 형식을 정확히 지켜서 답변하세요. 다른 설명은 절대 추가하지 마세요.\n"
    "견종: <내용>\n"
    "일기: <내용>"
)


def build_multi_prompt(dog_name: str, count: int) -> str:
    return MULTI_PROMPT_TEMPLATE.format(dog_name=dog_name, count=count)


VIDEO_PROMPT_TEMPLATE = (
    "이 영상은 반려견 '{dog_name}'의 짧은 동영상입니다. 영상 속 움직임과 소리를 참고해서 "
    "다음 두 가지를 작성해주세요.\n"
    "1. 견종 또는 견종 특징에 대한 아주 짧은 추정 (예: '말티푸로 추정', 알 수 없으면 '믹스견').\n"
    "2. 영상 속 상황을 바탕으로 반려견의 하루를 상상한 다정하고 짧은 일기 (2~3문장, 보호자 시점, 부드러운 존댓말).\n\n"
    "아래 형식을 정확히 지켜서 답변하세요. 다른 설명은 절대 추가하지 마세요.\n"
    "견종: <내용>\n"
    "일기: <내용>"
)


def build_video_prompt(dog_name: str) -> str:
    return VIDEO_PROMPT_TEMPLATE.format(dog_name=dog_name)


def parse_response(text: str) -> tuple[str, str]:
    breed_guess = "믹스견"
    diary = text.strip()
    for line in text.splitlines():
        line = line.strip()
        if line.startswith("견종:"):
            breed_guess = line.replace("견종:", "").strip()
        elif line.startswith("일기:"):
            diary = line.replace("일기:", "").strip()
    return breed_guess, diary


HIGHLIGHT_PROMPT_TEMPLATE = (
    "반려견 '{dog_name}'의 {month}월 일기 기록들입니다. 아래는 그 달에 쓰인 짧은 일기들이에요.\n\n"
    "{diary_list}\n\n"
    "위 일기들을 바탕으로, 이번 달 {dog_name}와 함께한 시간을 되돌아보는 따뜻한 월간 하이라이트를 "
    "5~7문장으로 써주세요. 보호자 시점, 부드러운 존댓말로, 그 달의 분위기나 특별했던 순간을 자연스럽게 "
    "엮어서 써주세요. 다른 설명 없이 하이라이트 본문만 답하세요."
)


def build_highlight_prompt(dog_name: str, month: str, diary_texts: list[str]) -> str:
    diary_list = "\n".join(f"- {text}" for text in diary_texts)
    return HIGHLIGHT_PROMPT_TEMPLATE.format(dog_name=dog_name, month=month, diary_list=diary_list)


SONG_PROMPT_TEMPLATE = (
    "반려견 '{dog_name}'에 대한 짧은 일기 기록들입니다.\n\n"
    "{diary_list}\n\n"
    "위 일기들의 분위기를 참고해서, {dog_name}에게 바치는 짧고 사랑스러운 노래 가사를 만들어주세요. "
    "1절(4줄)과 후렴(4줄) 정도의 짧은 분량으로, 한국어로, 밝고 다정한 느낌으로 써주세요. "
    "다른 설명 없이 가사 본문만 답하세요."
)


def build_song_prompt(dog_name: str, diary_texts: list[str]) -> str:
    diary_list = "\n".join(f"- {text}" for text in diary_texts)
    return SONG_PROMPT_TEMPLATE.format(dog_name=dog_name, diary_list=diary_list)


def build_identify_prompt(candidate_names: list[str]) -> str:
    numbered = "\n".join(f"{i + 2}번째 사진: {name}" for i, name in enumerate(candidate_names))
    return (
        "첫 번째 사진은 방금 새로 업로드된, 아직 이름이 확인되지 않은 반려견 사진입니다.\n"
        "그 뒤로 이어지는 사진들은 이미 등록된 반려견들의 얼굴 사진이며, 각각 누구인지 아래에 표시했습니다.\n\n"
        f"{numbered}\n\n"
        "첫 번째 사진 속 반려견이 이 중 누구와 같은 개체로 보이는지 판단해주세요. "
        "얼굴 생김새, 털 색, 무늬를 기준으로 비교하세요.\n"
        "확실히 같다고 판단되면 그 이름만 정확히 답하세요 (다른 설명 없이 이름만).\n"
        "누구와도 같아 보이지 않거나 확신이 서지 않으면 '없음'이라고만 답하세요."
    )
