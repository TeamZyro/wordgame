import html
import unicodedata
from pyrogram.types import InlineKeyboardMarkup
from bot.config import SUPPORT_GROUP, UPDATE_CHANNEL, TIME_ZONE
from bot.utils.emojis import (
    E_GAME,
    E_GRID,
    E_TOP,
    E_CROWN,
    E_BEST,
    E_LEVELUP,
    E_NEW,
    E_BOLT,
    E_CLOVER,
    E_VERIFIED,
    E_CHECK,
    E_CROSS,
    E_WARN,
    E_TIMER,
    E_CLOCK24,
    E_REFRESH,
    E_SEARCH,
    E_USER,
    E_ROBOT,
    E_SETTINGS,
    E_MEGAPHONE,
    E_CHAT,
    E_GIFT,
    E_WAVE,
    E_ANIME_CUTE,
    E_FILE,
    E_COMPOSE,
    E_PENCIL,
    E_STATS,
    ID_GAME,
    ID_GRID,
    ID_TOP,
    ID_CROWN,
    ID_CLOVER,
    ID_REFRESH,
    ID_STOP,
    ID_PLAY,
    ID_USER,
    ID_COMPOSE,
    ID_MEGAPHONE,
    ID_CHAT,
    ID_ADD,
    ID_STATS,
    ID_SETTINGS,
    ID_SHARE,
    ID_GIFT,
    ID_CLOCK24,
    ID_SKIP,
    make_button,
    make_api_button,
)


def normalize_fancy_telegram_name(name: str | None, max_len: int = 26) -> str:
    """Normalizes stylized Unicode fonts/symbols in Telegram names and HTML-escapes them."""
    if not name:
        return "Player"
    normalized = unicodedata.normalize("NFKC", str(name)).strip()
    cleaned = "".join(ch for ch in normalized if ch.isprintable())
    if not cleaned:
        cleaned = "Player"
    if len(cleaned) > max_len:
        cleaned = cleaned[: max_len - 1] + "…"
    return html.escape(cleaned)


def format_hint_pattern(word: str, revealed_indices: set[int] | None = None) -> str:
    """Creates a clean, single-spaced hint pattern for a Word Grid word."""
    w = word.upper().strip()
    n = len(w)
    if n <= 2:
        return " ".join(list(w))

    shown = {0, n - 1}
    if n >= 6:
        shown.add(n // 2)
    if revealed_indices:
        shown.update(revealed_indices)

    chars = [w[i] if i in shown else "_" for i in range(n)]
    return " ".join(chars)


def _fmt_tab(label: str, active: bool) -> str:
    return f"« {label} »" if active else label


def markup_dict_to_pyrogram(markup_dict: dict | None) -> InlineKeyboardMarkup | None:
    """Converts a Bot API reply_markup dict into a Kurigram InlineKeyboardMarkup (preserving custom icons)."""
    if not markup_dict or "inline_keyboard" not in markup_dict:
        return None
    pyro_rows = []
    for row in markup_dict["inline_keyboard"]:
        p_row = []
        for btn in row:
            raw_text = btn.get("text", "")
            text = "" if raw_text == "\u2060" else raw_text
            icon_id = btn.get("icon_custom_emoji_id")
            if "url" in btn:
                p_row.append(make_button(text, url=btn["url"], icon_id=icon_id))
            elif "switch_inline_query" in btn:
                p_row.append(
                    make_button(
                        text,
                        switch_inline_query=btn["switch_inline_query"],
                        icon_id=icon_id,
                    )
                )
            else:
                p_row.append(
                    make_button(
                        text,
                        callback_data=btn.get("callback_data", "noop"),
                        icon_id=icon_id,
                        fallback_prefix="🔄" if not text else "",
                    )
                )
        if p_row:
            pyro_rows.append(p_row)
    return InlineKeyboardMarkup(pyro_rows)


# ============================================================================
# WORD GRID ARCADE BOARD CAPTION & COMPACT KURIGRAM BUTTONS
# ============================================================================
def build_game_caption(game_data: dict, status_banner: str | None = None) -> str:
    round_num = game_data.get("round", 1)
    time_limit = game_data.get("time_limit", 60)
    theme_name = str(game_data.get("theme", "emerald")).upper()
    words_dict = game_data.get("words", {})
    total_words = len(words_dict)
    found_count = sum(1 for info in words_dict.values() if info.get("found_by"))
    hints_used = game_data.get("hints_used", 0)
    max_hints = game_data.get("max_hints", 3)

    lines = [
        f"{E_GRID} <b>WORD GRID — ROUND {round_num}</b>",
        f"{E_CLOVER} <code>{theme_name}</code>  •  {E_TIMER} <code>{time_limit}s</code>  •  {E_CHECK} <code>{found_count}/{total_words}</code>",
        "",
    ]

    word_lines = []
    for actual_word, info in words_dict.items():
        finder = info.get("found_by")
        if finder:
            safe_finder = normalize_fancy_telegram_name(finder, max_len=18)
            pts = info.get("points", 1)
            word_lines.append(
                f"{E_VERIFIED} <b>{html.escape(actual_word)}</b> — <i>{safe_finder} (+{pts})</i>"
            )
        else:
            hint_str = info.get("hint") or format_hint_pattern(actual_word, info.get("revealed"))
            word_lines.append(f"{E_SEARCH} <code>{hint_str}</code> <b>({len(actual_word)}L)</b>")

    lines.append("<blockquote>" + "\n".join(word_lines) + "</blockquote>")

    if status_banner:
        lines.append(f"\n{status_banner}")
    else:
        lines.append(
            f"\n{E_PENCIL} <i>Type a word in chat!</i>  •  {E_CLOVER} <b>Hints:</b> <code>{max_hints - hints_used}/{max_hints}</code>"
        )

    return "\n".join(lines)


def build_game_board_markup(solved: bool = False) -> InlineKeyboardMarkup:
    if solved:
        return InlineKeyboardMarkup(
            [
                [
                    make_button("Play Again", callback_data="game:new", icon_id=ID_PLAY, fallback_prefix="▶️"),
                    make_button("Ranks", callback_data="lb:users", icon_id=ID_TOP, fallback_prefix="🏆"),
                ]
            ]
        )
    return InlineKeyboardMarkup(
        [
            [
                make_button("Hint", callback_data="game:hint", icon_id=ID_CLOVER, fallback_prefix="💡"),
                make_button("Board", callback_data="game:refresh", icon_id=ID_REFRESH, fallback_prefix="🔄"),
                make_button("Stop", callback_data="game:stop", icon_id=ID_STOP, fallback_prefix="🛑"),
            ],
            [
                make_button("Leaderboard", callback_data="lb:users", icon_id=ID_TOP, fallback_prefix="🏆"),
            ],
        ]
    )


# ============================================================================
# BOT API 10.3 RICH MESSAGE HELP VIEW (Clean Mobile UI + <tg-button> Examples)
# ============================================================================
EXAMPLE_STYLE = {
    "correct": ' style="success"',
    "present": "",
    "absent": ' style="danger"',
}


def _example_button(state: str, letter: str) -> str:
    st_attr = EXAMPLE_STYLE.get(state, "")
    return f'<tg-button type="callback_data"{st_attr} data="wh:{state}:{letter}">{letter}</tg-button>'


def build_rich_help_html(section: str = "howto") -> str:
    """
    Returns Bot API 10.3 RichMessage HTML for `/help` and `help:*` callbacks,
    using `<tg-button>`, `<h3>`, `<h4>`, `<table bordered compact>`, and `<details>`.
    """
    if section == "grid":
        return (
            "<h3>How to Play Word Grid Arcade</h3>"
            "<blockquote>"
            "<ol>"
            "<li>Start a round in any group chat using /game</li>"
            "<li>Find words hidden horizontally, vertically, or diagonally on the 3D board</li>"
            "<li>Check the caption hints or tap the Hint button to reveal letters</li>"
            "<li>Type the word in chat to score points before the timer runs out</li>"
            "<li>Clear all words in time to advance to the next harder round!</li>"
            "</ol>"
            "</blockquote>"
            "<h4>Grid Commands</h4>"
            "<table bordered compact>"
            "<tr><th>Command</th><th>What it does</th></tr>"
            "<tr><td>/game</td><td>Start a 3D Word Grid round in a group</td></tr>"
            "<tr><td>/hint</td><td>Reveal a letter hint (up to 3 per round)</td></tr>"
            "<tr><td>/stopgame</td><td>Stop the active round and reset to Round 1</td></tr>"
            "<tr><td>/profile</td><td>View your combined Word Grid &amp; WordSeek card</td></tr>"
            "</table>"
        )

    if section == "scores":
        return (
            "<h3>Leaderboard &amp; Scores</h3>"
            "<h4>Quick Examples</h4>"
            "<blockquote>"
            "<table bordered compact>"
            "<tr><th>Command</th><th>What it shows</th></tr>"
            "<tr><td><code>/leaderboard</code></td><td>Group, today (5-letter)</td></tr>"
            "<tr><td><code>/leaderboard 4</code></td><td>4-letter, group, today</td></tr>"
            "<tr><td><code>/leaderboard global week 6</code></td><td>Global, this week, 6-letter</td></tr>"
            "<tr><td><code>/leaderboard month</code></td><td>This group's monthly board</td></tr>"
            "<tr><td><code>/score</code></td><td>Your score (group, today, 5-letter)</td></tr>"
            "<tr><td><code>/score 6</code></td><td>Your 6-letter stats</td></tr>"
            "<tr><td><code>/score @username global all 4</code></td><td>Full 4-letter global history for a user</td></tr>"
            "</table>"
            "</blockquote>"
            "<h4>Leaderboard Command</h4>"
            "<blockquote>"
            "<p><b>Syntax:</b> <code>/leaderboard [scope] [period] [length]</code></p>"
            "<table bordered compact>"
            "<tr><th>Parameter</th><th>Options</th></tr>"
            "<tr><td>Scope</td><td><code>group</code> (default), <code>global</code></td></tr>"
            "<tr><td>Period</td><td><code>today</code>, <code>week</code>, <code>month</code>, <code>year</code>, <code>all</code></td></tr>"
            "<tr><td>Length</td><td><code>4</code>, <code>5</code> (default), <code>6</code></td></tr>"
            "</table>"
            "</blockquote>"
        )

    if section == "group":
        return (
            "<h3>Group Settings (Admin Only)</h3>"
            "<h4>Authorized Users</h4>"
            "<blockquote>"
            "<p><b><code>/seekauth</code></b>: manage users who can end games without a vote.</p>"
            "<ul>"
            "<li><code>/seekauth @username</code>: authorize a user</li>"
            "<li><code>/seekauth remove @username</code>: remove authorization</li>"
            "<li><code>/seekauth list</code>: list all authorized users</li>"
            "</ul>"
            "</blockquote>"
            "<h4>Game Topic (Forum Groups)</h4>"
            "<details><summary><code>/setgametopic</code>: restrict games to topics</summary>"
            "<blockquote><p>Run this command inside the topic where you want games to be played.</p></blockquote>"
            "</details>"
            "<details><summary><code>/unsetgametopic</code>: remove topic restriction</summary>"
            "<blockquote><p>After unsetting, the bot can run games in any topic again.</p></blockquote>"
            "</details>"
            "<details><summary><code>/allowonlylen</code>: restrict word lengths</summary>"
            "<blockquote>"
            "<ul><li><code>/allowonlylen 4</code></li><li><code>/allowonlylen 5 6</code></li></ul>"
            "<p>The first number becomes the default length for <code>/new</code> in that topic.</p>"
            "</blockquote>"
            "</details>"
        )

    if section == "other":
        return (
            "<h3>Other Commands</h3>"
            "<blockquote>"
            "<p><b><code>/id</code></b>: get message, user, chat, and topic IDs.</p>"
            "<p><b><code>/profile</code></b>: view your combined Word Grid &amp; WordSeek profile card.</p>"
            "</blockquote>"
        )

    if section == "admin":
        return (
            "<h3>Admin Commands (Bot Owner Only)</h3>"
            "<blockquote>"
            "<table bordered compact>"
            "<tr><th>Command</th><th>What it does</th></tr>"
            "<tr><td><code>/panel</code></td><td>Open Admin Control Panel</td></tr>"
            "<tr><td><code>/stats</code></td><td>View live bot &amp; system stats</td></tr>"
            "<tr><td><code>/ban [user_id]</code></td><td>Ban a user from using the bot globally</td></tr>"
            "<tr><td><code>/unban [user_id]</code></td><td>Unban a previously banned user</td></tr>"
            "<tr><td><code>/transfer &lt;from&gt; &lt;to&gt;</code></td><td>Transfer WordSeek scores between users</td></tr>"
            "<tr><td><code>/broadcast</code></td><td>Broadcast replied message to all users &amp; groups</td></tr>"
            "</table>"
            "</blockquote>"
        )

    # Default: "howto"
    ex_s = _example_button("correct", "S")
    ex_t = _example_button("present", "T")
    ex_x = _example_button("absent", "X")
    ex_row = (
        _example_button("correct", "S")
        + _example_button("present", "T")
        + _example_button("absent", "A")
        + _example_button("absent", "R")
        + _example_button("correct", "E")
    )
    return (
        "<h3>How to Play WordSeek</h3>"
        "<blockquote>"
        "<ol>"
        "<li>Start a game using /new, /new4, /new5, or /new6</li>"
        "<li>Guess the hidden word</li>"
        "<li>After each guess, every letter becomes a colored button (see below)</li>"
        "<li>First person to guess correctly wins!</li>"
        "<li>Maximum 30 guesses per game</li>"
        "</ol>"
        "</blockquote>"
        "<h4>Reading the colors</h4>"
        f"<p>{ex_s} <b>Green</b>: right letter, right spot</p>"
        f"<p>{ex_t} <b>No color</b>: right letter, wrong spot</p>"
        f"<p>{ex_x} <b>Red</b>: letter isn't in the word</p>"
        "<p><i>Tap any letter button to see what it means. The no color button follows your Telegram theme.</i></p>"
        "<p><b>Example guess:</b></p>"
        f"<p>{ex_row}</p>"
        "<h4>Word Length Modes</h4>"
        "<blockquote>"
        "<ul>"
        "<li>/new: start the default 5-letter game</li>"
        "<li>/new 4: start a specific length (4, 5, or 6)</li>"
        "<li>/new4: start a 4-letter game</li>"
        "<li>/new5: start a 5-letter game</li>"
        "<li>/new6: start a 6-letter game</li>"
        "</ul>"
        "</blockquote>"
        "<h4>Basic Commands</h4>"
        "<table bordered compact>"
        "<tr><th>Command</th><th>What it does</th></tr>"
        "<tr><td>/new</td><td>Start a new WordSeek game (default 5L)</td></tr>"
        "<tr><td>/new4 /new5 /new6</td><td>Start a game with that length</td></tr>"
        "<tr><td>/end</td><td>End current game (voting or admin)</td></tr>"
        "<tr><td>/daily</td><td>Play Daily WordSeek (private chat only)</td></tr>"
        "<tr><td>/pausedaily</td><td>Pause Daily mode</td></tr>"
        "<tr><td>/game</td><td>Start 3D Word Grid Arcade (groups)</td></tr>"
        "</table>"
        "<details><summary>Daily Mode (Private Chat Only)</summary>"
        "<blockquote>"
        "<ul>"
        "<li>Start a daily game using /daily command</li>"
        "<li>One fixed 5-letter word per day with 6 guesses</li>"
        f"<li>Unlocks every day at 06:00 ({html.escape(TIME_ZONE)})</li>"
        "<li>If Daily is active, use /pausedaily to play normal WordSeek again</li>"
        "</ul>"
        "</blockquote>"
        "</details>"
    )


def build_help_keyboard_dict(
    is_admin: bool = False,
    active: str = "howto",
    show_back: bool = False,
) -> dict:
    """
    Builds Bot API 10.3 `reply_markup` dict with custom emoji icons,
    `"style": "primary"` on active tabs, and `"style": "success"` on support.
    """
    def _tab_btn(label: str, sec_key: str, icon_id: str | None = None) -> dict:
        is_act = active == sec_key
        return make_api_button(
            _fmt_tab(label, is_act),
            callback_data=f"help:{sec_key}",
            icon_id=icon_id,
            style="primary" if is_act else None,
        )

    rows = [
        [_tab_btn("How to Play", "howto", ID_GAME), _tab_btn("Word Grid", "grid", ID_GRID)],
        [_tab_btn("Scores", "scores", ID_TOP), _tab_btn("Group Setup", "group", ID_SETTINGS)],
        [_tab_btn("Other", "other", ID_COMPOSE)],
    ]
    if is_admin:
        rows[-1].append(_tab_btn("Admin", "admin", ID_CROWN))

    rows.append(
        [
            make_api_button("Updates", url=UPDATE_CHANNEL, icon_id=ID_MEGAPHONE),
            make_api_button("Support", url=SUPPORT_GROUP, icon_id=ID_CHAT, style="success"),
        ]
    )
    if show_back:
        rows.append([make_api_button("Back", callback_data="nav:home", icon_id=ID_SKIP)])

    return {"inline_keyboard": rows}


def build_help_view(
    bot_username: str,
    section: str = "howto",
    is_admin: bool = False,
    show_back: bool = True,
) -> tuple[str, InlineKeyboardMarkup]:
    """Kurigram premium HTML help view (used when editing a photo caption or fallback)."""
    kb_dict = build_help_keyboard_dict(is_admin=is_admin, active=section, show_back=show_back)
    pyro_markup = markup_dict_to_pyrogram(kb_dict)

    if section == "grid":
        text = (
            f"{E_GRID} <b>How to Play Word Grid Arcade</b>\n\n"
            f"<blockquote>"
            f"1. Send <code>/game</code> in a group chat to start Round 1.\n"
            f"2. Find words hidden horizontally, vertically, or diagonally.\n"
            f"3. Check caption hints like <code>A _ _ _ E (5L)</code> or tap <b>Hint</b>.\n"
            f"4. Type found words in chat to score points before time runs out!"
            f"</blockquote>"
        )
    elif section == "scores":
        text = (
            f"{E_TOP} <b>Leaderboard &amp; Scores</b>\n\n"
            f"<blockquote>"
            f"• <code>/leaderboard [global|group] [today|week|month|all] [4|5|6]</code>\n"
            f"• <code>/score [@user] [global|group] [today|week|month|all] [4|5|6]</code>\n"
            f"• <code>/profile</code> — Combined Word Grid &amp; WordSeek card"
            f"</blockquote>"
        )
    elif section == "group":
        text = (
            f"{E_SETTINGS} <b>Group Settings (Admin Only)</b>\n\n"
            f"<blockquote>"
            f"• <code>/seekauth @user</code> • <code>remove</code> • <code>list</code>\n"
            f"• <code>/setgametopic</code> &amp; <code>/unsetgametopic</code>\n"
            f"• <code>/allowonlylen 5 4 6</code>"
            f"</blockquote>"
        )
    elif section == "other":
        text = (
            f"{E_FILE} <b>Other Commands</b>\n\n"
            f"<blockquote>"
            f"• <code>/id</code> — View chat, user, topic, and message IDs\n"
            f"• <code>/profile</code> — View your combined player profile card"
            f"</blockquote>"
        )
    elif section == "admin":
        text = (
            f"{E_CROWN} <b>Admin Commands</b>\n\n"
            f"<blockquote>"
            f"• <code>/panel</code> • <code>/stats</code> • <code>/broadcast</code>\n"
            f"• <code>/ban [id]</code> • <code>/unban [id]</code> • <code>/transfer &lt;from&gt; &lt;to&gt;</code>"
            f"</blockquote>"
        )
    else:
        text = (
            f"{E_GAME} <b>How to Play WordSeek</b>\n\n"
            f"<blockquote>"
            f"1. Start a game using <code>/new</code>, <code>/new4</code>, <code>/new5</code>, or <code>/new6</code>.\n"
            f"2. Guess the hidden word — each letter becomes a colored button:\n"
            f"   {E_VERIFIED} <b>Green:</b> right letter, right spot\n"
            f"   {E_CLOVER} <b>Default:</b> right letter, wrong spot\n"
            f"   {E_CROSS} <b>Red:</b> letter isn't in the word\n"
            f"3. First player to guess wins! Max 30 guesses.\n"
            f"4. Use <code>/daily</code> in DM for the 6-try Word of the Day!"
            f"</blockquote>"
        )
    return text, pyro_markup


# ============================================================================
# SHARED START & PROFILE VIEWS (Kurigram Premium Emoji + Clean Card UI)
# ============================================================================
def build_start_view(
    first_name: str, bot_username: str, is_private: bool = True
) -> tuple[str, InlineKeyboardMarkup]:
    safe_name = normalize_fancy_telegram_name(first_name)
    uname = bot_username or "WordGridGameBot"

    if not is_private:
        text = (
            f"{E_GAME} <b>WordSeek &amp; Word Grid Ready!</b>\n\n"
            f"<blockquote>"
            f"{E_NEW} <b>WordSeek:</b> <code>/new</code> • <code>/new4</code> • <code>/new5</code> • <code>/new6</code> • <code>/end</code>\n"
            f"{E_GRID} <b>Word Grid:</b> <code>/game</code> • <code>/hint</code> • <code>/stopgame</code>\n"
            f"{E_TOP} <b>Ranks &amp; Scores:</b> <code>/leaderboard</code> • <code>/score</code>"
            f"</blockquote>"
        )
        markup = InlineKeyboardMarkup(
            [
                [
                    make_button("Start Seek", callback_data="ws:new:5", icon_id=ID_GAME, fallback_prefix="🟩"),
                    make_button("Start Grid", callback_data="game:new", icon_id=ID_GRID, fallback_prefix="🧩"),
                ],
                [
                    make_button("Ranks", callback_data="wslb:group:all:5", icon_id=ID_TOP, fallback_prefix="🏆"),
                    make_button("Help", callback_data="help:howto", icon_id=ID_COMPOSE, fallback_prefix="📖"),
                ],
            ]
        )
        return text, markup

    text = (
        f"{E_WAVE} <b>Welcome to WordSeek &amp; Word Grid!</b>\n\n"
        f"{E_ANIME_CUTE} Hey <b>{safe_name}</b>! Play competitive <b>WordSeek</b> (4L/5L/6L) and <b>3D Word Grid</b> right inside Telegram.\n\n"
        f"<blockquote>"
        f"{E_BOLT} <b>Quick Start</b>\n"
        f"• <code>/new</code> (<code>/new4</code> • <code>/new5</code> • <code>/new6</code>) — Start WordSeek\n"
        f"• <code>/daily</code> — WordSeek of the Day (6 attempts)\n"
        f"• <code>/game</code> — 3D Word Grid Arcade in groups\n"
        f"• <code>/help</code> — Rules, commands &amp; group setup"
        f"</blockquote>\n\n"
        f"{E_CLOVER} <i>Ready to test your vocabulary? Pick a mode below!</i>"
    )

    markup = InlineKeyboardMarkup(
        [
            [
                make_button(
                    "Add to Group",
                    url=f"https://t.me/{uname}?startgroup=true",
                    icon_id=ID_ADD,
                    fallback_prefix="➕",
                )
            ],
            [
                make_button("Play Seek", callback_data="ws:new:5", icon_id=ID_GAME, fallback_prefix="🟩"),
                make_button("Daily", callback_data="ws:daily", icon_id=ID_CLOCK24, fallback_prefix="🎯"),
            ],
            [
                make_button("Ranks", callback_data="wslb:global:all:5", icon_id=ID_TOP, fallback_prefix="🏆"),
                make_button("Profile", callback_data="nav:profile", icon_id=ID_USER, fallback_prefix="👤"),
                make_button("Help", callback_data="help:howto", icon_id=ID_COMPOSE, fallback_prefix="📖"),
            ],
            [
                make_button("Updates", url=UPDATE_CHANNEL, icon_id=ID_MEGAPHONE, fallback_prefix="📢"),
                make_button("Support", url=SUPPORT_GROUP, icon_id=ID_CHAT, fallback_prefix="💬"),
            ],
        ]
    )
    return text, markup


def build_profile_view(
    user_id: int,
    first_name: str,
    user_doc: dict | None,
    rank: int,
    seek_data: dict | None = None,
    show_back: bool = True,
) -> tuple[str, InlineKeyboardMarkup]:
    safe_name = normalize_fancy_telegram_name(first_name)
    grid_score = (user_doc or {}).get("score", 0)
    games_played = (user_doc or {}).get("games_played", 0)
    words_found = (user_doc or {}).get("words_found", games_played)
    best_round = (user_doc or {}).get("best_round", 1 if grid_score > 0 else 0)

    seek_score = (seek_data or {}).get("total_score", (user_doc or {}).get("seek_score", 0))
    seek_rank = (seek_data or {}).get("rank", 0)
    curr_streak = (seek_data or {}).get("current_streak", 0)
    high_streak = (seek_data or {}).get("highest_streak", 0)

    grid_rank_str = f"#{rank}" if rank > 0 else "Unranked"
    seek_rank_str = f"#{seek_rank}" if seek_rank > 0 else "Unranked"

    text = (
        f"{E_USER} <b>Player Profile — {safe_name}</b>\n\n"
        f"<blockquote>"
        f"{E_GAME} <b>WordSeek Stats (5L)</b>\n"
        f"├ {E_TOP} <b>Score:</b> <code>{seek_score:,} pts</code> ({seek_rank_str})\n"
        f"└ {E_BOLT} <b>Daily Streak:</b> <code>{curr_streak}d</code>  •  <b>Best:</b> <code>{high_streak}d</code>"
        f"</blockquote>\n"
        f"<blockquote>"
        f"{E_GRID} <b>Word Grid Arcade</b>\n"
        f"├ {E_CROWN} <b>Score:</b> <code>{grid_score:,} pts</code> ({grid_rank_str})\n"
        f"└ {E_CHECK} <b>Words:</b> <code>{words_found:,}</code>  •  <b>Best:</b> <code>Round {best_round}</code>"
        f"</blockquote>"
    )

    rows = [
        [
            make_button("Refresh", callback_data="profile:refresh", icon_id=ID_REFRESH, fallback_prefix="🔄"),
            make_button("Ranks", callback_data="wslb:global:all:5", icon_id=ID_TOP, fallback_prefix="🏆"),
        ]
    ]
    if show_back:
        rows.append([make_button("Back", callback_data="nav:home", icon_id=ID_SKIP, fallback_prefix="⬅️")])

    return text, InlineKeyboardMarkup(rows)


# ============================================================================
# BOT API 10.3 STYLED LEADERBOARD & SCORE KEYBOARDS (Icons + Color Styles)
# ============================================================================
def build_seek_filter_keyboard_dict(
    search_key: str,
    time_key: str,
    word_length: int,
    prefix: str = "wslb",
    include_game_switch: bool = False,
    show_back: bool = False,
) -> dict:
    """
    Sets `"style": "primary"` (Blue) on active filter buttons,
    `"style": "success"` (Green) on support, and custom emoji icons.
    """
    rows = []

    if include_game_switch:
        rows.append(
            [
                make_api_button(
                    "« WordSeek »",
                    callback_data=f"{prefix}:{search_key}:{time_key}:{word_length}",
                    icon_id=ID_GAME,
                    style="primary",
                ),
                make_api_button(
                    "Word Grid",
                    callback_data="lb:users",
                    icon_id=ID_GRID,
                ),
            ]
        )

    # Scope row: Global | Refresh | This chat
    g_btn = make_api_button(
        _fmt_tab("Global", search_key == "global"),
        callback_data=f"{prefix}:global:{time_key}:{word_length}",
        style="primary" if search_key == "global" else None,
    )
    ref_btn = make_api_button(
        "",
        callback_data=f"{prefix}:{search_key}:{time_key}:{word_length}:r",
        icon_id=ID_REFRESH,
    )
    c_btn = make_api_button(
        _fmt_tab("This chat", search_key == "group"),
        callback_data=f"{prefix}:group:{time_key}:{word_length}",
        style="primary" if search_key == "group" else None,
    )
    rows.append([g_btn, ref_btn, c_btn])

    # Time period rows (3 per row)
    time_items = [
        ("today", "Today"),
        ("week", "This week"),
        ("month", "This month"),
        ("year", "This year"),
        ("all", "All time"),
    ]
    t_row = []
    for t_k, t_label in time_items:
        t_row.append(
            make_api_button(
                _fmt_tab(t_label, time_key == t_k),
                callback_data=f"{prefix}:{search_key}:{t_k}:{word_length}",
                style="primary" if time_key == t_k else None,
            )
        )
        if len(t_row) == 3:
            rows.append(t_row)
            t_row = []
    if t_row:
        rows.append(t_row)

    # Word length row: 4 letters | 5 letters | 6 letters
    len_row = [
        make_api_button(
            _fmt_tab(f"{ln} letters", word_length == ln),
            callback_data=f"{prefix}:{search_key}:{time_key}:{ln}",
            style="primary" if word_length == ln else None,
        )
        for ln in (4, 5, 6)
    ]
    rows.append(len_row)

    rows.append(
        [
            make_api_button("Updates", url=UPDATE_CHANNEL, icon_id=ID_MEGAPHONE),
            make_api_button("Support", url=SUPPORT_GROUP, icon_id=ID_CHAT, style="success"),
        ]
    )

    if show_back:
        rows.append([make_api_button("Back", callback_data="nav:home", icon_id=ID_SKIP)])

    return {"inline_keyboard": rows}


def build_seek_score_view(
    score_data: dict | None,
    target_id: int,
    target_name: str,
    search_key: str = "global",
    time_key: str = "all",
    word_length: int = 5,
) -> tuple[str, InlineKeyboardMarkup, dict]:
    """Returns `(text_html, kurigram_markup, bot_api_styled_markup_dict)`."""
    safe_name = normalize_fancy_telegram_name((score_data or {}).get("name") or target_name)
    uname = (score_data or {}).get("username")
    mention = f'<a href="https://t.me/{uname}">{safe_name}</a>' if uname else safe_name
    scope_text = "globally" if search_key == "global" else "in this chat"

    if not score_data or (
        score_data.get("total_score", 0) == 0 and score_data.get("highest_streak", 0) == 0
    ):
        text = (
            f"{E_TOP} <b>WordSeek Scores ({word_length}L)</b>\n\n"
            f"<blockquote>"
            f"{E_USER} <b>{mention}</b> has no scores recorded {scope_text} for this period yet.\n"
            f"{E_NEW} <i>Start with <code>/new{word_length}</code> or play <code>/daily</code>!</i>"
            f"</blockquote>"
        )
    else:
        tot = score_data.get("total_score", 0)
        rnk = score_data.get("rank", 0)
        c_str = score_data.get("current_streak", 0)
        h_str = score_data.get("highest_streak", 0)
        text = (
            f"{E_TOP} <b>WordSeek Scores ({word_length}L)</b>\n\n"
            f"<blockquote>"
            f"{E_USER} <b>Player:</b> {mention}\n"
            f"{E_GIFT} <b>Total Score:</b> <code>{tot:,} pts</code> ({scope_text})\n"
            f"{E_CROWN} <b>Rank:</b> <code>#{rnk:,}</code>"
            f"</blockquote>\n"
            f"<blockquote>"
            f"{E_CLOCK24} <b>Daily WordSeek Streak</b>\n"
            f"├ {E_BOLT} <b>Current:</b> <code>{c_str} days</code>\n"
            f"└ {E_BEST} <b>Highest:</b> <code>{h_str} days</code>"
            f"</blockquote>"
        )

    prefix = f"wsscore:{target_id}"
    kb_dict = build_seek_filter_keyboard_dict(search_key, time_key, word_length, prefix=prefix)
    return text, markup_dict_to_pyrogram(kb_dict), kb_dict


def build_seek_leaderboard_view(
    entries: list[dict],
    search_key: str = "global",
    time_key: str = "all",
    word_length: int = 5,
    show_back: bool = False,
) -> tuple[str, InlineKeyboardMarkup, dict]:
    """Returns `(text_html, kurigram_markup, bot_api_styled_markup_dict)`."""
    scope_title = "Global" if search_key == "global" else "Group"
    header = f"{E_TOP} <b>{scope_title} WordSeek Leaderboard ({word_length}L)</b>\n\n"

    if not entries:
        body = (
            f"<blockquote>"
            f"{E_GAME} No scores recorded yet! Start a game with <code>/new{word_length}</code>."
            f"</blockquote>"
        )
    else:
        blocks: list[list[str]] = []
        for index, entry in enumerate(entries[:20]):
            if index == 0:
                rank_icon = f"{E_BEST}"
            elif index == 1:
                rank_icon = "🥈"
            elif index == 2:
                rank_icon = "🥉"
            else:
                rank_icon = f"<code>{index + 1}.</code>"

            name = normalize_fancy_telegram_name(entry.get("name", "Player"), max_len=24)
            uname = entry.get("username")
            uid = entry.get("user_id", 0)
            pts = entry.get("total_score", 0)

            if uname:
                user_link = f'<a href="https://t.me/{uname}">{name}</a>'
            elif uid:
                user_link = f'<a href="tg://user?id={uid}">{name}</a>'
            else:
                user_link = name

            line = f"{rank_icon} {user_link} — <b>{pts:,}</b> pts"
            if index == 0 or index == 3 or (index > 3 and (index - 3) % 10 == 0):
                blocks.append([])
            blocks[-1].append(line)

        body = "\n".join(f"<blockquote>{chr(10).join(b)}</blockquote>" for b in blocks)

    kb_dict = build_seek_filter_keyboard_dict(
        search_key=search_key,
        time_key=time_key,
        word_length=word_length,
        prefix="wslb",
        include_game_switch=True,
        show_back=show_back,
    )
    return header + body, markup_dict_to_pyrogram(kb_dict), kb_dict


def build_leaderboard_view(
    mode: str,
    entries: list[dict],
    show_back: bool = True,
) -> tuple[str, InlineKeyboardMarkup]:
    """Word Grid Arcade Leaderboard with Dual Game switcher to WordSeek Leaderboard."""
    if mode == "groups":
        header = f"{E_TOP} <b>Word Grid — Top Groups</b>\n\n"
        if not entries:
            body = f"<blockquote>{E_GRID} No groups have scored yet! Send <code>/game</code> in your group.</blockquote>"
        else:
            lines = []
            for idx, g in enumerate(entries[:10]):
                badge = E_BEST if idx == 0 else ("🥈" if idx == 1 else ("🥉" if idx == 2 else f"<code>{idx + 1}.</code>"))
                title = normalize_fancy_telegram_name(g.get("title", "Group"), max_len=24)
                score = g.get("score", 0)
                best_r = g.get("best_round", 1)
                lines.append(f"{badge} <b>{title}</b> — <code>{score:,}</code> pts <i>(R{best_r})</i>")
            body = "<blockquote>" + "\n".join(lines) + "</blockquote>"

        tabs = [
            make_button("Players", callback_data="lb:users", icon_id=ID_USER, fallback_prefix="👤"),
            make_button("« Groups »", callback_data="lb:groups", icon_id=ID_CHAT, fallback_prefix="👥"),
        ]
        refresh_cb = "lb:refresh:groups"
    else:
        header = f"{E_TOP} <b>Word Grid — Top Players</b>\n\n"
        if not entries:
            body = f"<blockquote>{E_GRID} No players have scored yet! Send <code>/game</code> to play.</blockquote>"
        else:
            lines = []
            for idx, u in enumerate(entries[:10]):
                badge = E_BEST if idx == 0 else ("🥈" if idx == 1 else ("🥉" if idx == 2 else f"<code>{idx + 1}.</code>"))
                name = normalize_fancy_telegram_name(u.get("first_name", "Player"), max_len=22)
                uid = u.get("user_id", 0)
                score = u.get("score", 0)
                user_link = f'<a href="tg://user?id={uid}">{name}</a>' if uid else f"<b>{name}</b>"
                lines.append(f"{badge} {user_link} — <code>{score:,}</code> pts")
            body = "<blockquote>" + "\n".join(lines) + "</blockquote>"

        tabs = [
            make_button("« Players »", callback_data="lb:users", icon_id=ID_USER, fallback_prefix="👤"),
            make_button("Groups", callback_data="lb:groups", icon_id=ID_CHAT, fallback_prefix="👥"),
        ]
        refresh_cb = "lb:refresh:users"

    rows = [
        [
            make_button("WordSeek", callback_data="wslb:global:all:5", icon_id=ID_GAME, fallback_prefix="🟩"),
            make_button("« Word Grid »", callback_data="lb:users", icon_id=ID_GRID, fallback_prefix="🧩"),
        ],
        tabs,
        [
            make_button("Refresh", callback_data=refresh_cb, icon_id=ID_REFRESH, fallback_prefix="🔄"),
            make_button("Profile", callback_data="nav:profile", icon_id=ID_USER, fallback_prefix="👤"),
        ],
    ]
    if show_back:
        rows.append([make_button("Back", callback_data="nav:home", icon_id=ID_SKIP, fallback_prefix="⬅️")])

    return header + body, InlineKeyboardMarkup(rows)


def build_admin_view(
    section: str = "home",
    total_users: int = 0,
    total_groups: int = 0,
    active_grid_games: int = 0,
    active_seek_games: int = 0,
) -> tuple[str, InlineKeyboardMarkup]:
    if section == "stats":
        text = (
            f"{E_STATS} <b>Bot Live Statistics</b>\n\n"
            f"<blockquote>"
            f"{E_USER} <b>Total Users:</b> <code>{total_users:,}</code>\n"
            f"{E_CHAT} <b>Total Groups:</b> <code>{total_groups:,}</code>\n"
            f"{E_GRID} <b>Active Grid Games:</b> <code>{active_grid_games}</code>\n"
            f"{E_GAME} <b>Active Seek Games:</b> <code>{active_seek_games}</code>"
            f"</blockquote>\n"
            f"{E_BOLT} <i>Motor pool &amp; TTL cache healthy.</i>"
        )
        markup = InlineKeyboardMarkup(
            [
                [
                    make_button("Refresh", callback_data="admin:stats", icon_id=ID_REFRESH, fallback_prefix="🔄"),
                    make_button("Back", callback_data="admin:home", icon_id=ID_SKIP, fallback_prefix="⬅️"),
                ]
            ]
        )
        return text, markup

    if section == "broadcast":
        text = (
            f"{E_MEGAPHONE} <b>Admin Broadcast</b>\n\n"
            f"<blockquote>"
            f"Reply to any message with <code>/broadcast</code> to send it to all users and groups with FloodWait protection.\n\n"
            f"{E_CROWN} <b>Owner Commands:</b>\n"
            f"• <code>/stats</code> — Detailed system &amp; runtime metrics\n"
            f"• <code>/ban [user_id]</code> &amp; <code>/unban [user_id]</code>\n"
            f"• <code>/transfer &lt;from_id&gt; &lt;to_id&gt;</code>"
            f"</blockquote>"
        )
        markup = InlineKeyboardMarkup(
            [[make_button("Back", callback_data="admin:home", icon_id=ID_SKIP, fallback_prefix="⬅️")]]
        )
        return text, markup

    text = (
        f"{E_CROWN} <b>Admin Control Panel</b>\n\n"
        f"<blockquote>"
        f"{E_ROBOT} Manage Word Grid Arcade &amp; WordSeek statistics, active games, user moderation, and broadcasts."
        f"</blockquote>"
    )
    markup = InlineKeyboardMarkup(
        [
            [
                make_button("Stats", callback_data="admin:stats", icon_id=ID_STATS, fallback_prefix="📊"),
                make_button("Broadcast", callback_data="admin:broadcast", icon_id=ID_MEGAPHONE, fallback_prefix="📢"),
            ]
        ]
    )
    return text, markup
