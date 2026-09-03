import os

from . import database


def get(key: str, default: str = "") -> str:
    """DB(settings 테이블)에 값이 있으면 그걸 쓰고, 없으면 .env(환경변수)를 대체로 씁니다."""
    db_value = database.get_setting(key)
    if db_value:
        return db_value
    return os.environ.get(key, default)


def get_bool(key: str, default: bool = False) -> bool:
    value = get(key, "1" if default else "0")
    return value.strip() == "1"
