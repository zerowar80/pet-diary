from . import claude_provider, common, gemini_provider, openai_provider

PROVIDERS = {
    "claude": {"label": "Claude (Anthropic)", "module": claude_provider},
    "gemini": {"label": "Gemini (Google)", "module": gemini_provider},
    "chatgpt": {"label": "ChatGPT (OpenAI)", "module": openai_provider},
}

DEFAULT_PROVIDER = "claude"


def _module_for(provider: str):
    if provider not in PROVIDERS:
        provider = DEFAULT_PROVIDER
    return PROVIDERS[provider]["module"]


def generate_diary_entry(photo_path: str, dog_name: str, provider: str) -> tuple[str, str]:
    return _module_for(provider).generate(photo_path, dog_name)


def generate_diary_entry_multi(photo_paths: list[str], dog_name: str, provider: str) -> tuple[str, str]:
    """여러 장의 사진을 한 번에 보고 하나의 일기로 만들어줍니다."""
    prompt = common.build_multi_prompt(dog_name, len(photo_paths))
    text = _module_for(provider).generate_text(prompt, image_paths=photo_paths)
    return common.parse_response(text)


def generate_diary_entry_video(video_path: str, dog_name: str, provider: str) -> tuple[str, str]:
    """동영상을 직접 이해해서 일기를 생성합니다. 현재는 Gemini만 지원합니다."""
    if provider != "gemini":
        raise NotImplementedError("이 AI는 동영상을 직접 분석하지 못합니다.")
    return gemini_provider.generate_video(video_path, dog_name)


def generate_monthly_highlight(dog_name: str, month: str, diary_texts: list[str], provider: str) -> str:
    prompt = common.build_highlight_prompt(dog_name, month, diary_texts)
    return _module_for(provider).generate_text(prompt)


def generate_song_lyrics(dog_name: str, diary_texts: list[str], provider: str) -> str:
    prompt = common.build_song_prompt(dog_name, diary_texts)
    return _module_for(provider).generate_text(prompt)


def identify_dog(photo_path: str, candidates: list[dict], provider: str) -> str | None:
    """candidates: [{"name": str, "photo_path": str}, ...]
    새 사진(photo_path)이 candidates 중 누구와 같은 개체인지 AI에게 물어보고,
    확실히 일치하는 이름을 찾으면 그 이름을, 아니면 None을 반환합니다."""
    if not candidates:
        return None
    prompt = common.build_identify_prompt([c["name"] for c in candidates])
    image_paths = [photo_path] + [c["photo_path"] for c in candidates]
    result = _module_for(provider).generate_text(prompt, image_paths=image_paths)
    result = result.strip()
    for c in candidates:
        if c["name"] == result or c["name"] in result:
            return c["name"]
    return None
