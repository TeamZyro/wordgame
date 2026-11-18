import os
import json
import random
import string
import logging
from functools import lru_cache
from io import BytesIO
from PIL import Image, ImageDraw, ImageFont
from bot.utils.views import format_hint_pattern

logger = logging.getLogger("WordGridBot.ImageGen")

WORDS_JSON_PATH = os.path.join(os.path.dirname(__file__), "words.json")
FONT_PATH = os.path.join(os.path.dirname(__file__), "GameFont.ttf")

DEFAULT_WORDS = [
    "CAT", "DOG", "SUN", "SKY", "SEA", "ICE", "GEM", "KEY", "MAP", "OWL", "FOX",
    "BEAR", "LION", "WOLF", "HAWK", "STAR", "MOON", "FIRE", "WIND", "RAIN", "SNOW",
    "GOLD", "JADE", "RUBY", "OPAL", "TREE", "LEAF", "ROSE", "LAKE", "REEF", "WAVE",
    "SHIP", "BOOK", "HARP", "DRUM", "GAME", "MAZE", "CLUE", "HERO", "KING", "MAGE",
    "APPLE", "TIGER", "WATER", "EAGLE", "SHARK", "WHALE", "PANDA", "KOALA", "ZEBRA",
    "FLAME", "STORM", "CLOUD", "FROST", "OCEAN", "RIVER", "SWORD", "ARMOR", "CROWN",
    "JEWEL", "PEARL", "CORAL", "AMBER", "TOPAZ", "PIANO", "FLUTE", "MAGIC", "QUEST",
    "PLANET", "GALAXY", "NEBULA", "ROCKET", "COMET", "METEOR", "DRAGON", "KNIGHT",
    "CASTLE", "SHIELD", "FALCON", "PYTHON", "JUNGLE", "FOREST", "DESERT", "CANYON",
    "ISLAND", "VALLEY", "BRIDGE", "TEMPLE", "PALACE", "TROPHY", "LEGEND", "ARCADE",
    "PUZZLE", "RIDDLE", "CIPHER", "VORTEX", "MATRIX", "CRYSTAL", "EMERALD", "DIAMOND",
    "THUNDER", "VOLCANO", "GLACIER", "RAINBOW", "SUNRISE", "PHOENIX", "GRIFFIN",
    "DOLPHIN", "PENGUIN", "PANTHER", "LEOPARD", "CHEETAH", "OCTOPUS", "COMPASS",
    "LANTERN", "HARVEST", "JOURNEY", "VICTORY", "CHAMPION", "TREASURE", "SAPPHIRE",
]

BLOCKED_TOKENS = {
    "JAN", "FEB", "MAR", "APR", "JUN", "JUL", "AUG", "SEP", "OCT", "NOV", "DEC",
    "MON", "TUE", "WED", "THU", "FRI", "SAT", "SUN", "DVD", "USA", "NON", "SAN",
    "FAX", "RSS", "FAQ", "URL", "EUR", "PDF", "USR", "COM", "PRE", "LTD", "LOS",
    "INC", "TEL", "EST", "III", "GMT", "XML", "INT", "USB", "PHP", "ETC", "MSN",
    "LAS", "MIN", "PST", "TOM", "BOB", "DEV", "VOL", "LEE", "WWW", "LLC", "SEC",
    "IBM", "JIM", "DEL", "JOE", "CDS", "CVS", "DES", "LCD", "AVE", "PIC", "VHS",
    "CON", "UPS", "VAR", "DOC", "USD", "LES", "ANN", "DAN", "BBC", "AVG", "ROM",
    "SRC", "HIV", "PDA", "DSL", "ZUM", "DNA", "TIM", "SQL", "DON", "GPS", "ACC",
    "GNU", "BEN", "AOL", "LIB", "UTC", "DER", "PER", "VIA", "PRO", "MAX", "ADS",
    "GAY", "DIE", "SEX", "ASS", "XXX", "VIRGIN", "PORN", "NUDE", "EBAY", "PERL",
    "HTML", "HTTP", "JPEG", "MPEG", "ISBN", "ISSN", "PMID",
}


def load_word_list() -> list[str]:
    try:
        if os.path.exists(WORDS_JSON_PATH):
            with open(WORDS_JSON_PATH, "r", encoding="utf-8") as f:
                raw = json.load(f)
            cleaned = sorted(
                {
                    str(w).strip().upper()
                    for w in raw
                    if str(w).strip().isalpha()
                    and 3 <= len(str(w).strip()) <= 8
                    and str(w).strip().upper() not in BLOCKED_TOKENS
                },
                key=lambda x: (len(x), x),
            )
            if len(cleaned) >= 100:
                return cleaned
    except Exception as e:
        logger.warning("Failed to load words.json, using fallback bank: %s", e)
    return DEFAULT_WORDS[:]


WORD_LIST = load_word_list()

WORDS_BY_LEN: dict[int, list[str]] = {}
for _w in WORD_LIST:
    WORDS_BY_LEN.setdefault(len(_w), []).append(_w)

THEMES = {
    "emerald": {
        "bg": (11, 24, 17),
        "header_bg": (16, 38, 26),
        "board_glow": (52, 211, 153),
        "top_text": (167, 243, 208),
        "cell_fill": (20, 58, 38),
        "cell_shadow": (7, 22, 13),
        "text_col": (220, 252, 231),
    },
    "ocean": {
        "bg": (10, 19, 34),
        "header_bg": (15, 30, 54),
        "board_glow": (56, 189, 248),
        "top_text": (186, 230, 253),
        "cell_fill": (22, 54, 94),
        "cell_shadow": (8, 20, 40),
        "text_col": (224, 242, 254),
    },
    "sunset": {
        "bg": (32, 14, 18),
        "header_bg": (48, 20, 26),
        "board_glow": (251, 146, 60),
        "top_text": (254, 215, 170),
        "cell_fill": (88, 38, 32),
        "cell_shadow": (38, 14, 10),
        "text_col": (255, 237, 213),
    },
    "royal": {
        "bg": (20, 12, 32),
        "header_bg": (32, 18, 52),
        "board_glow": (192, 132, 252),
        "top_text": (233, 213, 255),
        "cell_fill": (62, 30, 96),
        "cell_shadow": (24, 10, 40),
        "text_col": (243, 232, 255),
    },
    "crimson": {
        "bg": (28, 10, 16),
        "header_bg": (44, 16, 24),
        "board_glow": (244, 63, 94),
        "top_text": (254, 205, 211),
        "cell_fill": (84, 24, 38),
        "cell_shadow": (36, 8, 14),
        "text_col": (255, 228, 230),
    },
    "cyber": {
        "bg": (12, 14, 28),
        "header_bg": (20, 24, 48),
        "board_glow": (45, 212, 191),
        "top_text": (153, 246, 228),
        "cell_fill": (28, 36, 74),
        "cell_shadow": (10, 14, 34),
        "text_col": (204, 251, 241),
    },
    "gold": {
        "bg": (26, 20, 10),
        "header_bg": (42, 32, 14),
        "board_glow": (250, 204, 21),
        "top_text": (254, 240, 138),
        "cell_fill": (78, 58, 22),
        "cell_shadow": (32, 22, 8),
        "text_col": (254, 249, 195),
    },
    "arctic": {
        "bg": (14, 24, 34),
        "header_bg": (22, 38, 52),
        "board_glow": (125, 211, 252),
        "top_text": (224, 242, 254),
        "cell_fill": (32, 62, 84),
        "cell_shadow": (12, 26, 38),
        "text_col": (240, 249, 255),
    },
}

FOUND_PALETTE = [
    ((239, 68, 68), (145, 28, 28)),
    ((34, 197, 94), (18, 115, 52)),
    ((59, 130, 246), (26, 72, 155)),
    ((217, 70, 239), (126, 28, 145)),
    ((234, 179, 8), (140, 102, 4)),
    ((6, 182, 212), (8, 105, 126)),
    ((249, 115, 22), (154, 58, 10)),
    ((139, 92, 246), (78, 42, 158)),
    ((236, 72, 153), (142, 30, 88)),
    ((20, 184, 166), (12, 108, 96)),
    ((132, 204, 22), (74, 120, 10)),
    ((99, 102, 241), (48, 50, 150)),
    ((244, 63, 94), (148, 24, 48)),
    ((14, 165, 233), (8, 95, 140)),
]


@lru_cache(maxsize=16)
def get_cached_font(size: int):
    try:
        if os.path.exists(FONT_PATH):
            return ImageFont.truetype(FONT_PATH, size)
    except Exception as e:
        logger.warning("Could not load GameFont.ttf at size %s: %s", size, e)
    return ImageFont.load_default()


def _text_metrics(draw: ImageDraw.ImageDraw, text: str, font) -> tuple[int, int, int]:
    if hasattr(font, "getbbox"):
        bbox = font.getbbox(text)
        return bbox[2] - bbox[0], bbox[3] - bbox[1], bbox[1]
    w, h = draw.textsize(text, font=font)
    return w, h, 0


def create_single_hint(word: str, revealed_indices: set[int] | None = None) -> str:
    return format_hint_pattern(word, revealed_indices)


def place_word(word_to_place: str, grid: list[list[str]], size: int, force_type: str = "any"):
    all_directions = [(0, 1), (1, 0), (1, 1), (1, -1)]
    if force_type == "cross":
        directions = [(1, 1), (1, -1)]
    elif force_type == "plus":
        directions = [(0, 1), (1, 0)]
    else:
        directions = all_directions[:]

    random.shuffle(directions)
    wlen = len(word_to_place)

    best_candidate = None
    best_overlap = -1

    for dr, dc in directions:
        valid_starts = []
        for r in range(size):
            for c in range(size):
                end_r = r + (wlen - 1) * dr
                end_c = c + (wlen - 1) * dc
                if 0 <= end_r < size and 0 <= end_c < size:
                    valid_starts.append((r, c))

        random.shuffle(valid_starts)

        for row, col in valid_starts:
            overlap = 0
            can_place = True
            for i, letter in enumerate(word_to_place):
                curr_r = row + i * dr
                curr_c = col + i * dc
                existing = grid[curr_r][curr_c]
                if existing != "" and existing != letter:
                    can_place = False
                    break
                if existing == letter:
                    overlap += 1

            if can_place and overlap < wlen:
                if overlap > best_overlap:
                    best_overlap = overlap
                    best_candidate = (row, col, dr, dc)
                    if overlap >= 1:
                        break
        if best_overlap >= 1 and best_candidate is not None:
            break

    if best_candidate is None:
        return None

    row, col, dr, dc = best_candidate
    positions = []
    for i, letter in enumerate(word_to_place):
        curr_r = row + i * dr
        curr_c = col + i * dc
        grid[curr_r][curr_c] = letter
        positions.append((curr_r, curr_c))
    return positions


def _select_non_substring_words(pool: list[str], count: int) -> list[str]:
    candidates = random.sample(pool, min(len(pool), count * 4))
    selected: list[str] = []
    for w in candidates:
        if any(w in other or other in w for other in selected):
            continue
        selected.append(w)
        if len(selected) == count:
            break
    if len(selected) < count:
        for w in candidates:
            if w not in selected:
                selected.append(w)
                if len(selected) == count:
                    break
    return selected


def create_new_game_state(word_count: int = 3, round_num: int = 1):
    if word_count <= 2:
        size = 5
    elif word_count <= 4:
        size = 6
    elif word_count <= 6:
        size = 7
    elif word_count <= 8:
        size = 8
    elif word_count <= 11:
        size = 9
    else:
        size = 10

    if round_num <= 2:
        min_len, max_len = 3, 4
    elif round_num <= 5:
        min_len, max_len = 4, 5
    elif round_num <= 10:
        min_len, max_len = 4, 6
    elif round_num <= 20:
        min_len, max_len = 5, 7
    elif round_num <= 35:
        min_len, max_len = 5, 8
    else:
        min_len, max_len = 6, 8

    max_len = min(max_len, size)
    min_len = min(min_len, max_len)

    valid_words: list[str] = []
    for length in range(min_len, max_len + 1):
        valid_words.extend(WORDS_BY_LEN.get(length, []))

    if len(valid_words) < word_count * 2:
        for length in range(3, size + 1):
            valid_words.extend(WORDS_BY_LEN.get(length, []))
        valid_words = list(dict.fromkeys(valid_words))

    best_grid = None
    best_words_info = {}

    for _attempt in range(25):
        grid = [["" for _ in range(size)] for _ in range(size)]
        words_info = {}
        actual_count = min(word_count, len(valid_words))
        target_words = _select_non_substring_words(valid_words, actual_count)
        target_words.sort(key=len, reverse=True)

        palette = FOUND_PALETTE[:]
        random.shuffle(palette)
        mixture = ["cross", "plus", "any", "cross", "plus", "any"]
        random.shuffle(mixture)

        for idx, word in enumerate(target_words):
            force_type = mixture[idx % len(mixture)]
            positions = place_word(word, grid, size, force_type)
            if not positions and force_type != "any":
                positions = place_word(word, grid, size, "any")

            if positions:
                col_idx = idx % len(palette)
                words_info[word] = {
                    "positions": positions,
                    "color": palette[col_idx][0],
                    "shadow": palette[col_idx][1],
                }

        if len(words_info) > len(best_words_info):
            best_grid = [row[:] for row in grid]
            best_words_info = dict(words_info)

        if len(words_info) >= actual_count:
            break

    grid = best_grid if best_grid is not None else [["" for _ in range(size)] for _ in range(size)]
    words_info = best_words_info

    filler_pool = "AAEEIIOOUURRSSRTTLNNLLCCDDMMPBGHHFFYYWKV"
    for r in range(size):
        for c in range(size):
            if grid[r][c] == "":
                grid[r][c] = random.choice(filler_pool)

    theme_name = random.choice(list(THEMES.keys()))
    return grid, words_info, theme_name


def render_grid_image(
    grid: list[list[str]],
    words_info: dict,
    found_words: list[str],
    round_num: int = 1,
    category: str = "ARCADE",
    theme_name: str = "emerald",
) -> BytesIO:
    theme = THEMES.get(theme_name, THEMES["emerald"])

    size = len(grid)
    cell_size = 104 if size <= 7 else (94 if size <= 9 else 86)

    margin_side = 46
    margin_top = 148
    margin_bottom = 46

    grid_width = size * cell_size + margin_side * 2
    grid_height = size * cell_size + margin_top + margin_bottom

    img = Image.new("RGB", (grid_width, grid_height), color=theme["bg"])
    draw = ImageDraw.Draw(img)

    # Balanced, non-oversized typography for header and 3D tile buttons
    font_title = get_cached_font(34)
    font_sub = get_cached_font(20)
    font_letter = get_cached_font(int(cell_size * 0.44))

    draw.rounded_rectangle(
        [20, 16, grid_width - 20, 122],
        radius=16,
        fill=theme["header_bg"],
        outline=theme["board_glow"],
        width=2,
    )

    title_text = f"{category.upper()} WORD GRID"
    title_w, _, _ = _text_metrics(draw, title_text, font_title)
    draw.text(
        ((grid_width - title_w) / 2, 28),
        title_text,
        fill=theme["top_text"],
        font=font_title,
    )

    sub_text = f"Round {round_num}   •   Theme: {theme_name.title()}   •   Found: {len(found_words)}/{len(words_info)}"
    sub_w, _, _ = _text_metrics(draw, sub_text, font_sub)
    draw.text(
        ((grid_width - sub_w) / 2, 80),
        sub_text,
        fill=theme["text_col"],
        font=font_sub,
    )

    rect_pad = 12
    draw.rounded_rectangle(
        [
            margin_side - rect_pad,
            margin_top - rect_pad,
            margin_side + size * cell_size + rect_pad,
            margin_top + size * cell_size + rect_pad,
        ],
        radius=20,
        fill=theme["cell_shadow"],
        outline=theme["board_glow"],
        width=4,
    )

    cell_highlight: dict[tuple[int, int], tuple[tuple[int, int, int], tuple[int, int, int]]] = {}
    for fw in found_words:
        if fw in words_info:
            f_col = words_info[fw]["color"]
            s_col = words_info[fw]["shadow"]
            for pos in words_info[fw]["positions"]:
                cell_highlight[tuple(pos)] = (f_col, s_col)

    for row in range(size):
        for col in range(size):
            letter = grid[row][col]
            x0 = margin_side + col * cell_size
            y0 = margin_top + row * cell_size

            cx0, cy0 = x0 + 6, y0 + 6
            cx1, cy1 = x0 + cell_size - 6, y0 + cell_size - 6

            if (row, col) in cell_highlight:
                fill_col, shadow_col = cell_highlight[(row, col)]
                txt_col = (255, 255, 255)
            else:
                fill_col = theme["cell_fill"]
                shadow_col = theme["cell_shadow"]
                txt_col = theme["text_col"]

            draw.rounded_rectangle([cx0 + 2, cy0 + 6, cx1 + 2, cy1 + 6], radius=14, fill=shadow_col)
            draw.rounded_rectangle([cx0, cy0, cx1, cy1], radius=14, fill=fill_col)

            lighter_shade = tuple(min(255, c + 38) for c in fill_col)
            draw.rounded_rectangle(
                [cx0 + 2, cy0 + 2, cx1 - 2, cy1 - 2],
                radius=12,
                outline=lighter_shade,
                width=2,
            )

            text_w, text_h, y_offset = _text_metrics(draw, letter, font_letter)
            tx = cx0 + ((cx1 - cx0) - text_w) / 2
            ty = cy0 + ((cy1 - cy0) - text_h) / 2 - y_offset

            draw.text((tx, ty), letter, fill=txt_col, font=font_letter)

    img_io = BytesIO()
    img.save(img_io, format="PNG", optimize=True)
    img_io.name = "grid.png"
    img_io.seek(0)
    return img_io
