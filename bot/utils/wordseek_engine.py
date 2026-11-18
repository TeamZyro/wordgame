import os
import json
import html
import random
import logging
from collections import deque
from functools import lru_cache
from io import BytesIO
from PIL import Image, ImageDraw, ImageFont
from bot.utils.image_gen import WORDS_BY_LEN, FONT_PATH

logger = logging.getLogger("WordGridBot.WordSeekEngine")

DATA_DIR = os.path.join(os.path.dirname(__file__), "wordseek_data")
ROBOTO_FONT_PATH = os.path.join(os.path.dirname(__file__), "roboto.ttf")

# Zero-width characters used by WordSeek so identical letter buttons in a row are uniquely rendered
ZERO_WIDTH = [
    "\u200B",  # zero width space
    "\u200C",  # zero width non-joiner
    "\u200D",  # zero width joiner
    "\u2060",  # word joiner
    "\uFEFF",  # zero width no-break space
]

# Bot API 10.3 RichTextButton / RichMessageButton styles
BUTTON_STYLE: dict[str, str | None] = {
    "correct": "success",  # Green button (right letter, right spot)
    "present": None,       # Default theme button (right letter, wrong spot)
    "absent": "danger",    # Red button (letter not in word)
}

MODE_LABEL: dict[int, str] = {
    4: "4-letter mode",
    5: "5-letter mode",
    6: "6-letter mode",
}

FANCY_MAP = {
    "0": "𝟬", "1": "𝟭", "2": "𝟮", "3": "𝟯", "4": "𝟰",
    "5": "𝟱", "6": "𝟲", "7": "𝟳", "8": "𝟴", "9": "𝟵",
    "A": "𝗔", "B": "𝗕", "C": "𝗖", "D": "𝗗", "E": "𝗘",
    "F": "𝗙", "G": "𝗚", "H": "𝗛", "I": "𝗜", "J": "𝗝",
    "K": "𝗞", "L": "𝗟", "M": "𝗠", "N": "𝗡", "O": "𝗢",
    "P": "𝗣", "Q": "𝗤", "R": "𝗥", "S": "𝗦", "T": "𝗧",
    "U": "𝗨", "V": "𝗩", "W": "𝗪", "X": "𝗫", "Y": "𝗬", "Z": "𝗭",
    "a": "𝗮", "b": "𝗯", "c": "𝗰", "d": "𝗱", "e": "𝗲",
    "f": "𝗳", "g": "𝗴", "h": "𝗵", "i": "𝗶", "j": "𝗷",
    "k": "𝗸", "l": "𝗹", "m": "𝗺", "n": "𝗻", "o": "𝗼",
    "p": "𝗽", "q": "𝗾", "r": "𝗿", "s": "𝘀", "t": "𝘁",
    "u": "𝘂", "v": "𝘃", "w": "𝘄", "x": "𝘅", "y": "𝘆", "z": "𝘇",
}


def to_fancy_text(text: str) -> str:
    return "".join(FANCY_MAP.get(ch, ch) for ch in text)


def zero_width_noise(min_count: int = 1, max_count: int = 6) -> str:
    count = random.randint(min_count, max_count)
    return "".join(random.choice(ZERO_WIDTH) for _ in range(count))


def _load_json_list(filename: str, fallback_len: int) -> list[str]:
    path = os.path.join(DATA_DIR, filename)
    try:
        if os.path.exists(path):
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
            if isinstance(data, list) and data:
                return [str(w).strip().lower() for w in data if str(w).strip().isalpha()]
    except Exception as e:
        logger.warning("Failed to load %s: %s", filename, e)
    return [w.lower() for w in WORDS_BY_LEN.get(fallback_len, ["game", "word", "play"])]


def _load_common_words_dict() -> dict:
    path = os.path.join(DATA_DIR, "commonWords.json")
    try:
        if os.path.exists(path):
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
            if isinstance(data, dict):
                return data
    except Exception as e:
        logger.warning("Failed to load commonWords.json: %s", e)
    return {}


COMMON_WORDS: dict[int, list[str]] = {
    4: _load_json_list("common-four.json", 4),
    5: _load_json_list("common-five.json", 5),
    6: _load_json_list("common-six.json", 6),
}

ALL_VALID_WORDS: dict[int, set[str]] = {
    4: set(_load_json_list("all-four.json", 4)) | set(COMMON_WORDS[4]) | {w.lower() for w in WORDS_BY_LEN.get(4, [])},
    5: set(_load_json_list("all-five.json", 5)) | set(COMMON_WORDS[5]) | {w.lower() for w in WORDS_BY_LEN.get(5, [])},
    6: set(_load_json_list("all-six.json", 6)) | set(COMMON_WORDS[6]) | {w.lower() for w in WORDS_BY_LEN.get(6, [])},
}

DAILY_WORD_LIST: list[str] = _load_json_list("daily-word-lists.json", 5) or COMMON_WORDS[5]
COMMON_WORDS_DETAILS: dict = _load_common_words_dict()

_CHAT_WORD_HISTORY: dict[tuple[int, int], deque[str]] = {}


def select_random_seek_word(chat_id: int, word_length: int = 5) -> str:
    pool = COMMON_WORDS.get(word_length) or COMMON_WORDS[5]
    key = (int(chat_id), int(word_length))
    if len(_CHAT_WORD_HISTORY) > 500:
        _CHAT_WORD_HISTORY.clear()

    history = _CHAT_WORD_HISTORY.get(key)
    if history is None:
        history = deque(maxlen=50)
        _CHAT_WORD_HISTORY[key] = history

    used = set(history)
    available = [w for w in pool if w not in used]
    if len(available) < 10:
        history.clear()
        available = pool

    chosen = random.choice(available).lower()
    history.append(chosen)
    return chosen


def is_valid_seek_guess(word: str, word_length: int = 5) -> bool:
    w = word.strip().lower()
    if len(w) != word_length or not w.isalpha():
        return False
    valid_set = ALL_VALID_WORDS.get(word_length, set())
    return w in valid_set


def evaluate_guess(guess: str, solution: str) -> list[str]:
    """
    Evaluates a WordSeek guess against `solution`.
    Returns a list of states: `'correct'` (green), `'present'` (default/yellow), or `'absent'` (red).
    """
    g = guess.upper()
    s = solution.upper()
    length = len(s)

    remaining: dict[str, int] = {}
    for ch in s:
        remaining[ch] = remaining.get(ch, 0) + 1

    result = ["absent"] * length

    for i in range(min(len(g), length)):
        if g[i] == s[i]:
            result[i] = "correct"
            remaining[g[i]] -= 1

    for i in range(min(len(g), length)):
        if result[i] == "absent" and remaining.get(g[i], 0) > 0:
            result[i] = "present"
            remaining[g[i]] -= 1

    return result


def render_guess_row(guess: str, solution: str) -> str:
    """
    Exact port of `renderGuessRow` from WordSeek's `src/handlers/on-message.tsx`!
    Produces Bot API 10.3 `<tg-button>` (`RichTextButton`) elements inside `<p>` with
    `style="success"` (Green), default (no style), and `style="danger"` (Red).
    """
    states = evaluate_guess(guess, solution)
    buttons = []
    for idx, letter in enumerate(guess.upper()):
        state = states[idx]
        style = BUTTON_STYLE.get(state)
        style_attr = f' style="{style}"' if style else ""
        label = f"{zero_width_noise()}{letter}{zero_width_noise()}"
        buttons.append(
            f'<tg-button type="callback_data"{style_attr} data="wh:{state}:{letter}">{label}</tg-button>'
        )
    return f"<p>{''.join(buttons)}</p>"


def build_rich_feedback(guesses: list[str], solution: str, max_guesses: int = 30) -> str:
    """
    Exact port of `buildRichFeedback` from WordSeek's `src/handlers/on-message.tsx`!
    Returns Bot API 10.3 RichMessage HTML where ONLY colored `<tg-button>` rows are shown.
    """
    mode_label = MODE_LABEL.get(len(solution), f"{len(solution)}-letter mode")
    rows = "".join(render_guess_row(g, solution) for g in guesses)
    return f"<h3>{mode_label}</h3><p><i>{len(guesses)}/{max_guesses} guesses</i></p>{rows}"


def format_guess_emoji_row(guess: str, solution: str) -> str:
    """Fallback emoji row if a custom Bot API root doesn't support RichMessage."""
    states = evaluate_guess(guess, solution)
    emoji_map = {"correct": "🟩", "present": "🟨", "absent": "🟥"}
    squares = "".join(emoji_map[st] for st in states)
    spaced_letters = " ".join(to_fancy_text(guess.upper()))
    return f"{squares}  <b>{spaced_letters}</b>"


def format_word_details(word: str, custom_details: dict | None = None) -> str:
    """Renders WordSeek word definition, IPA pronunciation, and example sentence in HTML."""
    w_low = word.strip().lower()
    details = custom_details or COMMON_WORDS_DETAILS.get(w_low) or {}

    meaning = details.get("meaning")
    phonetic = details.get("phonetic") or details.get("pronunciation")
    sentence = details.get("sentence") or details.get("example")

    parts = [f"<strong>Correct Word: {html.escape(word)}</strong>"]
    if phonetic:
        parts.append(f"<strong>{html.escape(word.capitalize())}</strong> <code>{html.escape(str(phonetic))}</code>")
    if meaning:
        parts.append(f"<strong>Meaning</strong>: {html.escape(str(meaning))}")
    if sentence:
        parts.append(f"<strong>Example</strong>: {html.escape(str(sentence))}")

    return "<blockquote>" + "\n".join(parts) + "</blockquote>"


def generate_wordle_share_text(day_number: int, guesses: list[str], solution: str) -> str:
    attempt_line = f"{day_number} {len(guesses)}/6"
    lines = []
    for g in guesses:
        states = evaluate_guess(g, solution)
        row = "".join("🟩" if st == "correct" else ("🟨" if st == "present" else "⬛") for st in states)
        lines.append(row)
    return f"WordSeek {attempt_line}\n\n" + "\n".join(lines) + "\nTry yourself by using /daily command."


@lru_cache(maxsize=8)
def _get_wordle_font(size: int):
    for fp in (ROBOTO_FONT_PATH, FONT_PATH):
        if os.path.exists(fp):
            try:
                return ImageFont.truetype(fp, size)
            except Exception:
                pass
    return ImageFont.load_default()


def render_wordseek_image(guesses: list[str], solution: str, max_rows: int = 6) -> BytesIO:
    """Pillow port of WordSeek's `generateWordleImage` for `/daily` mode."""
    word_len = len(solution)
    total_rows = max(max_rows, len(guesses))

    tile_size = 60
    gap = 8
    padding = 20

    width = padding * 2 + word_len * tile_size + (word_len - 1) * gap
    height = padding * 2 + total_rows * tile_size + (total_rows - 1) * gap

    img = Image.new("RGB", (width, height), color=(18, 18, 19))
    draw = ImageDraw.Draw(img)
    font = _get_wordle_font(30)

    color_map = {
        "correct": (83, 141, 78),
        "present": (181, 159, 59),
        "absent": (58, 58, 60),
        "empty": (18, 18, 19),
    }

    for row_idx in range(total_rows):
        if row_idx < len(guesses):
            guess_str = guesses[row_idx].upper()
            states = evaluate_guess(guess_str, solution)
        else:
            guess_str = " " * word_len
            states = ["empty"] * word_len

        for col_idx in range(word_len):
            x0 = padding + col_idx * (tile_size + gap)
            y0 = padding + row_idx * (tile_size + gap)
            x1 = x0 + tile_size
            y1 = y0 + tile_size

            st = states[col_idx]
            fill_rgb = color_map.get(st, (58, 58, 60))

            if st == "empty":
                draw.rectangle([x0, y0, x1, y1], fill=fill_rgb, outline=(86, 87, 88), width=2)
            else:
                draw.rectangle([x0, y0, x1, y1], fill=fill_rgb)

            ch = guess_str[col_idx].strip() if col_idx < len(guess_str) else ""
            if ch:
                if hasattr(font, "getbbox"):
                    bbox = font.getbbox(ch)
                    tw = bbox[2] - bbox[0]
                    th = bbox[3] - bbox[1]
                    y_off = bbox[1]
                else:
                    tw, th = draw.textsize(ch, font=font)
                    y_off = 0
                tx = x0 + (tile_size - tw) / 2
                ty = y0 + (tile_size - th) / 2 - y_off
                draw.text((tx, ty), ch, fill=(255, 255, 255), font=font)

    img_io = BytesIO()
    img.save(img_io, format="PNG", optimize=True)
    img_io.name = "wordseek.png"
    img_io.seek(0)
    return img_io
