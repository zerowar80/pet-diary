from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

FONTS_DIR = Path(__file__).resolve().parent / "static" / "fonts"
FONT_LABEL = FONTS_DIR / "NanumGothicExtraBold.ttf"
FONT_TEXT = FONTS_DIR / "NanumPen.ttf"

CONTENT_WIDTH = 760
MARGIN = 44
LINE_HEIGHT = 52
GAP = 6
MAX_SINGLE_PHOTO_HEIGHT = 900
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


def _square_crop(path: Path, size: int) -> Image.Image:
    img = Image.open(path).convert("RGB")
    w, h = img.size
    side = min(w, h)
    left = (w - side) // 2
    top = (h - side) // 2
    return img.crop((left, top, left + side, top + side)).resize((size, size), Image.LANCZOS)


def _build_photo_block(photo_paths: list[Path]) -> Image.Image:
    """앨범에서 보이는 것처럼 사진을 그대로(1장이면 원본 비율, 여러 장이면 그리드로) 배치합니다."""
    if len(photo_paths) <= 1:
        img = Image.open(photo_paths[0]).convert("RGB")
        w, h = img.size
        new_h = round(CONTENT_WIDTH * h / w)
        if new_h > MAX_SINGLE_PHOTO_HEIGHT:
            # 너무 세로로 길면(파노라마 등) 정사각형으로 잘라서 과도하게 길어지는 것을 막습니다.
            return _square_crop(photo_paths[0], CONTENT_WIDTH)
        return img.resize((CONTENT_WIDTH, max(new_h, 1)), Image.LANCZOS)

    cols = 2 if len(photo_paths) == 2 else 3
    cell = (CONTENT_WIDTH - GAP * (cols - 1)) // cols
    rows = (len(photo_paths) + cols - 1) // cols
    block_h = cell * rows + GAP * (rows - 1)
    block = Image.new("RGB", (CONTENT_WIDTH, block_h), PAPER_COLOR)
    for i, path in enumerate(photo_paths):
        thumb = _square_crop(path, cell)
        r, c = divmod(i, cols)
        block.paste(thumb, (c * (cell + GAP), r * (cell + GAP)))
    return block


def create_polaroid(
    photo_paths: list[Path], dog_name: str, date_str: str, diary_text: str, output_path: Path
) -> None:
    """사진(들) + 날짜 + 일기를 폴라로이드 스타일 한 장짜리 이미지로 만들어 저장합니다."""
    photo_block = _build_photo_block(photo_paths)
    photo_h = photo_block.height

    label_font = ImageFont.truetype(str(FONT_LABEL), 30)
    name_font = ImageFont.truetype(str(FONT_LABEL), 38)
    text_font = ImageFont.truetype(str(FONT_TEXT), 40)

    probe_canvas = Image.new("RGB", (10, 10))
    probe_draw = ImageDraw.Draw(probe_canvas)
    diary_lines = _wrap_text(probe_draw, diary_text.strip() or " ", text_font, CONTENT_WIDTH)

    caption_top_pad = 34
    header_height = 54
    caption_height = caption_top_pad + header_height + len(diary_lines) * LINE_HEIGHT + 60

    canvas_w = CONTENT_WIDTH + MARGIN * 2
    canvas_h = MARGIN + photo_h + caption_height

    canvas = Image.new("RGB", (canvas_w, canvas_h), PAPER_COLOR)
    canvas.paste(photo_block, (MARGIN, MARGIN))

    draw = ImageDraw.Draw(canvas)
    caption_top = MARGIN + photo_h + caption_top_pad

    draw.text((MARGIN, caption_top), dog_name, font=name_font, fill=INK_COLOR)
    name_width = draw.textlength(dog_name, font=name_font)
    draw.text((MARGIN + name_width + 16, caption_top + 6), date_str, font=label_font, fill=MUSTARD_COLOR)

    y = caption_top + header_height
    for line in diary_lines:
        draw.text((MARGIN, y), line, font=text_font, fill=INK_COLOR)
        y += LINE_HEIGHT

    canvas.save(output_path, "JPEG", quality=92)
