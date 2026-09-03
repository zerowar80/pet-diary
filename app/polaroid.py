from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

FONTS_DIR = Path(__file__).resolve().parent / "static" / "fonts"
FONT_LABEL = FONTS_DIR / "NanumGothicExtraBold.ttf"
FONT_TEXT = FONTS_DIR / "NanumPen.ttf"

PHOTO_SIZE = 760
MARGIN = 44
LINE_HEIGHT = 52
PAPER_COLOR = (255, 253, 248)
INK_COLOR = (43, 33, 26)
MUSTARD_COLOR = (201, 138, 44)


def _wrap_text(draw: ImageDraw.ImageDraw, text: str, font: ImageFont.FreeTypeFont, max_width: int) -> list[str]:
    lines = []
    for paragraph in text.splitlines() or [""]:
        words = paragraph.split(" ")
        current = ""
        for word in words:
            trial = (current + " " + word).strip()
            if draw.textlength(trial, font=font) <= max_width or not current:
                current = trial
            else:
                lines.append(current)
                current = word
        lines.append(current)
    return lines


def create_polaroid(photo_path: Path, dog_name: str, date_str: str, diary_text: str, output_path: Path) -> None:
    """사진 + 날짜 + 일기를 폴라로이드 스타일 한 장짜리 이미지로 만들어 저장합니다."""
    photo = Image.open(photo_path).convert("RGB")
    w, h = photo.size
    side = min(w, h)
    left = (w - side) // 2
    top = (h - side) // 2
    photo = photo.crop((left, top, left + side, top + side)).resize(
        (PHOTO_SIZE, PHOTO_SIZE), Image.LANCZOS
    )

    label_font = ImageFont.truetype(str(FONT_LABEL), 30)
    name_font = ImageFont.truetype(str(FONT_LABEL), 38)
    text_font = ImageFont.truetype(str(FONT_TEXT), 40)

    probe_canvas = Image.new("RGB", (10, 10))
    probe_draw = ImageDraw.Draw(probe_canvas)
    content_width = PHOTO_SIZE
    diary_lines = _wrap_text(probe_draw, diary_text.strip() or " ", text_font, content_width)

    caption_top_pad = 34
    header_height = 54
    caption_height = caption_top_pad + header_height + len(diary_lines) * LINE_HEIGHT + 60

    canvas_w = PHOTO_SIZE + MARGIN * 2
    canvas_h = MARGIN + PHOTO_SIZE + caption_height

    canvas = Image.new("RGB", (canvas_w, canvas_h), PAPER_COLOR)
    canvas.paste(photo, (MARGIN, MARGIN))

    draw = ImageDraw.Draw(canvas)
    caption_top = MARGIN + PHOTO_SIZE + caption_top_pad

    draw.text((MARGIN, caption_top), dog_name, font=name_font, fill=INK_COLOR)
    name_width = draw.textlength(dog_name, font=name_font)
    draw.text((MARGIN + name_width + 16, caption_top + 6), date_str, font=label_font, fill=MUSTARD_COLOR)

    y = caption_top + header_height
    for line in diary_lines:
        draw.text((MARGIN, y), line, font=text_font, fill=INK_COLOR)
        y += LINE_HEIGHT

    canvas.save(output_path, "JPEG", quality=92)
