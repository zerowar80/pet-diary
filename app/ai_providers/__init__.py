from . import claude_provider, gemini_provider, openai_provider

PROVIDERS = {
    "claude": {"label": "Claude (Anthropic)", "module": claude_provider},
    "gemini": {"label": "Gemini (Google)", "module": gemini_provider},
    "chatgpt": {"label": "ChatGPT (OpenAI)", "module": openai_provider},
}

DEFAULT_PROVIDER = "claude"


def generate_diary_entry(photo_path: str, dog_name: str, provider: str) -> tuple[str, str]:
    if provider not in PROVIDERS:
        provider = DEFAULT_PROVIDER
    module = PROVIDERS[provider]["module"]
    return module.generate(photo_path, dog_name)
