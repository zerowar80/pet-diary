import json
import urllib.request

from . import settings

# WMO 날씨 코드 -> 이모지 매핑 (Open-Meteo 기준)
# https://open-meteo.com/en/docs 의 weathercode 표를 참고했습니다.
WEATHER_CODE_EMOJI = {
    0: "☀️",
    1: "🌤️",
    2: "⛅",
    3: "☁️",
    45: "🌫️",
    48: "🌫️",
    51: "🌦️",
    53: "🌦️",
    55: "🌦️",
    56: "🌧️",
    57: "🌧️",
    61: "🌧️",
    63: "🌧️",
    65: "🌧️",
    66: "🌧️",
    67: "🌧️",
    71: "🌨️",
    73: "🌨️",
    75: "🌨️",
    77: "🌨️",
    80: "🌦️",
    81: "🌧️",
    82: "⛈️",
    85: "🌨️",
    86: "🌨️",
    95: "⛈️",
    96: "⛈️",
    99: "⛈️",
}


def get_current_weather_emoji() -> str | None:
    """.env에 WEATHER_LAT/WEATHER_LON이 설정되어 있으면 현재 날씨 이모지를 반환하고,
    설정이 없거나 조회에 실패하면 None을 반환합니다 (호출 측에서 장식용 아이콘으로 대체)."""
    lat = settings.get("WEATHER_LAT").strip()
    lon = settings.get("WEATHER_LON").strip()
    if not lat or not lon:
        return None

    url = (
        "https://api.open-meteo.com/v1/forecast"
        f"?latitude={lat}&longitude={lon}&current_weather=true"
    )
    try:
        with urllib.request.urlopen(url, timeout=5) as response:
            data = json.loads(response.read().decode("utf-8"))
        code = data.get("current_weather", {}).get("weathercode")
        return WEATHER_CODE_EMOJI.get(code, "⛅")
    except Exception:  # noqa: BLE001
        return None
