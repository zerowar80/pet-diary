from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

FONTS_DIR = Path(__file__).resolve().parent / "static" / "fonts"
FONT_LABEL = FONTS_DIR / "NanumGothicExtraBold.ttf"
FONT_TEXT = FONTS_DIR / "NanumPen.ttf"
FONT_EMOJI = FONTS_DIR / "NotoColorEmoji.ttf"

CARD_WIDTH = 760
GAP = 6
MAX_SINGLE_PHOTO_HEIGHT = 900

PAPER_COLOR = (255, 253, 248)
POLAROID_BORDER_COLOR = (255, 253, 248)
INK_COLOR = (43, 33, 26)
INK_FAINT = (43, 33, 26)  # opacity 는 아래에서 alpha-blend 로 흉내냅니다.
MUSTARD_COLOR = (201, 138, 44)

# 폴라로이드 바깥 여백 (아래쪽을 조금 더 두껍게 - 인화지 느낌)
BORDER_SIDE = 34
BORDER_TOP = 34
BORDER_BOTTOM = 60


def _blend(color, ratio, bg=PAPER_COLOR):
    return tuple(round(c * ratio + b * (1 - ratio)) for c, b in zip(color, bg))


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
    if len(photo_paths) <= 1:
        img = Image.open(photo_paths[0]).convert("RGB")
        w, h = img.size
        new_h = round(CARD_WIDTH * h / w)
        if new_h > MAX_SINGLE_PHOTO_HEIGHT:
            return _square_crop(photo_paths[0], CARD_WIDTH)
        return img.resize((CARD_WIDTH, max(new_h, 1)), Image.LANCZOS)

    cols = 2 if len(photo_paths) == 2 else 3
    cell = (CARD_WIDTH - GAP * (cols - 1)) // cols
    rows = (len(photo_paths) + cols - 1) // cols
    block_h = cell * rows + GAP * (rows - 1)
    block = Image.new("RGB", (CARD_WIDTH, block_h), (255, 255, 255))
    for i, path in enumerate(photo_paths):
        thumb = _square_crop(path, cell)
        r, c = divmod(i, cols)
        block.paste(thumb, (c * (cell + GAP), r * (cell + GAP)))
    return block


def _grid_paper(width: int, height: int) -> Image.Image:
    """일기 텍스트 영역의 옅은 격자 배경(공책 느낌)을 그립니다."""
    layer = Image.new("RGB", (width, height), PAPER_COLOR)
    draw = ImageDraw.Draw(layer)
    grid_color = _blend(INK_COLOR, 0.09)
    step = 22
    for x in range(0, width, step):
        draw.line([(x, 0), (x, height)], fill=grid_color, width=1)
    for y in range(0, height, step):
        draw.line([(0, y), (width, y)], fill=grid_color, width=1)
    return layer


def create_polaroid(
    photo_paths: list[Path],
    dog_name: str,
    date_str: str,
    diary_text: str,
    output_path: Path,
    weather_emoji: str | None = None,
) -> None:
    """실제 일기 카드(DATE/TITLE 바 + 사진 + 일기)를 그대로 재현하고, 바깥에 폴라로이드 테두리를 둘러 저장합니다."""
    label_font = ImageFont.truetype(str(FONT_LABEL), 20)
    date_font = ImageFont.truetype(str(FONT_TEXT), 24)
    title_font = ImageFont.truetype(str(FONT_TEXT), 30)
    text_font = ImageFont.truetype(str(FONT_TEXT), 32)

    probe = ImageDraw.Draw(Image.new("RGB", (10, 10)))

    # ---- 사진 블록 ----
    photo_block = _build_photo_block(photo_paths)

    # ---- 일기 텍스트 줄바꿈 ----
    text_pad_x = 22
    diary_lines = _wrap_text(probe, diary_text.strip() or " ", text_font, CARD_WIDTH - text_pad_x * 2)
    line_height = 46
    diary_box_h = 26 + len(diary_lines) * line_height + 20

    # ---- 카드 각 구간 높이 ----
    date_row_h = 54
    title_row_h = 52
    card_h = date_row_h + title_row_h + photo_block.height + diary_box_h

    # ---- 카드(테두리 안쪽) 그리기 ----
    card = Image.new("RGB", (CARD_WIDTH, card_h), PAPER_COLOR)
    draw = ImageDraw.Draw(card)

    # DATE 줄
    draw.line([(0, date_row_h), (CARD_WIDTH, date_row_h)], fill=INK_COLOR, width=2)
    date_box_w = int(CARD_WIDTH * 0.72)
    draw.line([(date_box_w, 0), (date_box_w, date_row_h)], fill=INK_COLOR, width=2)
    draw.text((18, 16), "DATE.", font=label_font, fill=_blend(INK_COLOR, 0.55))
    label_w = draw.textlength("DATE.", font=label_font)
    draw.text((18 + label_w + 10, 13), date_str, font=date_font, fill=INK_COLOR)
    if weather_emoji:
        try:
            emoji_size = 32
            emoji_font = ImageFont.truetype(str(FONT_EMOJI), 109)
            tmp = Image.new("RGBA", (136, 128), (0, 0, 0, 0))
            tmp_draw = ImageDraw.Draw(tmp)
            tmp_draw.text((0, 0), weather_emoji, font=emoji_font, embedded_color=True)
            bbox = tmp.getbbox()
            if bbox:
                tmp = tmp.crop(bbox)
                ratio = emoji_size / max(tmp.size)
                tmp = tmp.resize((max(1, round(tmp.width * ratio)), max(1, round(tmp.height * ratio))), Image.LANCZOS)
                card.paste(tmp, (date_box_w + 20, 14), tmp)
        except Exception:  # noqa: BLE001
            pass  # 이모지 렌더링에 실패하면 조용히 생략합니다.

    # TITLE 줄
    title_top = date_row_h
    draw.line([(0, title_top + title_row_h), (CARD_WIDTH, title_top + title_row_h)], fill=INK_COLOR, width=2)
    draw.text((18, title_top + 14), "TITLE.", font=label_font, fill=MUSTARD_COLOR)
    tlabel_w = draw.textlength("TITLE.", font=label_font)
    draw.text((18 + tlabel_w + 10, title_top + 8), f"{dog_name}의 하루", font=title_font, fill=INK_COLOR)

    # 사진
    photo_top = title_top + title_row_h
    card.paste(photo_block, (0, photo_top))
    draw.line([(0, photo_top + photo_block.height), (CARD_WIDTH, photo_top + photo_block.height)], fill=INK_COLOR, width=2)

    # 일기 텍스트 (격자 배경)
    diary_top = photo_top + photo_block.height
    grid_bg = _grid_paper(CARD_WIDTH, diary_box_h)
    card.paste(grid_bg, (0, diary_top))
    y = diary_top + 22
    for line in diary_lines:
        draw.text((text_pad_x, y), line, font=text_font, fill=INK_COLOR)
        y += line_height

    # 카드 바깥 테두리
    draw.rectangle([(0, 0), (CARD_WIDTH - 1, card_h - 1)], outline=INK_COLOR, width=2)

    # ---- 폴라로이드 테두리 씌우기 ----
    canvas_w = CARD_WIDTH + BORDER_SIDE * 2
    canvas_h = card_h + BORDER_TOP + BORDER_BOTTOM
    canvas = Image.new("RGB", (canvas_w, canvas_h), POLAROID_BORDER_COLOR)
    canvas.paste(card, (BORDER_SIDE, BORDER_TOP))

    canvas.save(output_path, "JPEG", quality=92)
