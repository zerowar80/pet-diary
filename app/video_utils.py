import shutil
import subprocess
from pathlib import Path


def is_available() -> bool:
    return shutil.which("ffmpeg") is not None and shutil.which("ffprobe") is not None


def get_duration_seconds(video_path: str) -> float | None:
    """영상 길이(초)를 반환합니다. ffprobe가 없거나 실패하면 None을 반환합니다."""
    if not shutil.which("ffprobe"):
        return None
    try:
        result = subprocess.run(
            [
                "ffprobe", "-v", "error",
                "-show_entries", "format=duration",
                "-of", "default=noprint_wrappers=1:nokey=1",
                video_path,
            ],
            capture_output=True, text=True, timeout=15,
        )
        return float(result.stdout.strip())
    except Exception:  # noqa: BLE001
        return None


def extract_thumbnail_frame(video_path: str, output_path: str, at_seconds: float = 1.0) -> bool:
    """영상의 특정 시점 프레임을 이미지로 추출합니다. 성공하면 True."""
    if not shutil.which("ffmpeg"):
        return False
    try:
        subprocess.run(
            [
                "ffmpeg", "-y",
                "-ss", str(at_seconds),
                "-i", video_path,
                "-frames:v", "1",
                "-q:v", "2",
                output_path,
            ],
            capture_output=True, timeout=20,
        )
        return Path(output_path).exists() and Path(output_path).stat().st_size > 0
    except Exception:  # noqa: BLE001
        return False
