import html
import unicodedata
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from bot.config import SUPPORT_GROUP, UPDATE_CHANNEL, TIME_ZONE


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
    """Converts a Bot API reply_markup dict into a Pyrogram InlineKeyboardMarkup for fallback."""
    if not markup_dict or "inline_keyboard" not in markup_dict:
        return None
    pyro_rows = []
    for row in markup_dict["inline_keyboard"]:
        p_row = []
        for btn in row:
            if "url" in btn:
                p_row.append(InlineKeyboardButton(btn["text"], url=btn["url"]))
            elif "switch_inline_query" in btn:
                p_row.append(
                    InlineKeyboardButton(
                        btn["text"], switch_inline_query=btn["switch_inline_query"]
                    )
                )
            else:
                p_row.append(
                    InlineKeyboardButton(
                        btn["text"], callback_data=btn.get("callback_data", "noop")
                    )
                )
        if p_row:
            pyro_rows.append(p_row)
    return InlineKeyboardMarkup(pyro_rows)


# ============================================================================
# WORD GRID ARCADE BOARD CAPTION & COMPACT BUTTONS
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
        f"🧩 <b>WORD GRID — ROUND {round_num}</b>",
        f"🎨 <code>{theme_name}</code>  •  ⏱ <code>{time_limit}s</code>  •  🎯 <code>{found_count}/{total_words}</code>",
        "",
    ]

    word_lines = []
    for actual_word, info in words_dict.items():
        finder = info.get("found_by")
        if finder:
            safe_finder = normalize_fancy_telegram_name(finder, max_len=18)
            pts = info.get("points", 1)
            word_lines.append(f"✅ <b>{html.escape(actual_word)}</b> — <i>{safe_finder} (+{pts})</i>")
        else:
            hint_str = info.get("hint") or format_hint_pattern(actual_word, info.get("revealed"))
            word_lines.append(f"💡 <code>{hint_str}</code> <b>({len(actual_word)}L)</b>")

    lines.append("<blockquote>" + "\n".join(word_lines) + "</blockquote>")

    if status_banner:
        lines.append(f"\n{status_banner}")
    else:
        lines.append(
            f"\n💬 <i>Type a word in chat!</i>  •  💡 <b>Hints:</b> <code>{max_hints - hints_used}/{max_hints}</code>"
        )

    return "\n".join(lines)


def build_game_board_markup(solved: bool = False) -> InlineKeyboardMarkup:
    if solved:
        return InlineKeyboardMarkup(
            [
                [
                    InlineKeyboardButton("▶️ Play Again", callback_data="game:new"),
                    InlineKeyboardButton("🏆 Ranks", callback_data="lb:users"),
                ]
            ]
        )
    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton("💡 Hint", callback_data="game:hint"),
                InlineKeyboardButton("🔄 Board", callback_data="game:refresh"),
                InlineKeyboardButton("🛑 Stop", callback_data="game:stop"),
            ],
            [
                InlineKeyboardButton("🏆 Ranks", callback_data="lb:users"),
            ],
        ]
    )


# ============================================================================
# BOT API 10.3 RICH MESSAGE HELP VIEW (Ported 1:1 from WordSeek-master/src/commands/help.ts)
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
    Returns Bot API 10.3 RichMessage HTML for `/help` and `help_*` callbacks,
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

    # Default: "howto" — exact port of getHowToPlayMessage() from WordSeek-master/src/commands/help.ts
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
    Builds Bot API 10.3 `reply_markup` dict with `"style": "primary"` on active tabs
    and `"style": "success"` on action buttons, matching WordSeek-master's `getMainHelpKeyboard`.
    """
    def _tab_btn(label: str, sec_key: str) -> dict:
        is_act = active == sec_key
        btn = {
            "text": _fmt_tab(label, is_act),
            "callback_data": f"help:{sec_key}",
        }
        if is_act:
            btn["style"] = "primary"
        return btn

    rows = [
        [_tab_btn("How to Play", "howto"), _tab_btn("Word Grid", "grid")],
        [_tab_btn("Scores", "scores"), _tab_btn("Group Settings", "group")],
        [_tab_btn("Other Commands", "other")],
    ]
    if is_admin:
        rows[-1].append(_tab_btn("👑 Admin", "admin"))

    rows.append(
        [
            {"text": "📢 Updates", "url": UPDATE_CHANNEL},
            {"text": "💬 Support", "url": SUPPORT_GROUP, "style": "success"},
        ]
    )
    if show_back:
        rows.append([{"text": "⬅️ Back", "callback_data": "nav:home"}])

    return {"inline_keyboard": rows}


def build_help_view(
    bot_username: str,
    section: str = "howto",
    is_admin: bool = False,
    show_back: bool = True,
) -> tuple[str, InlineKeyboardMarkup]:
    """Fallback Pyrogram HTML help view when editing a photo caption (such as from /start)."""
    uname = bot_username or "WordGridGameBot"
    kb_dict = build_help_keyboard_dict(is_admin=is_admin, active=section, show_back=show_back)
    pyro_markup = markup_dict_to_pyrogram(kb_dict)

    if section == "grid":
        text = (
            "🧩 <b>How to Play Word Grid Arcade</b>\n\n"
            "<blockquote>"
            "1. Send <code>/game</code> in a group chat to start Round 1.\n"
            "2. Find words hidden horizontally, vertically, or diagonally.\n"
            "3. Check the caption for hints like <code>A _ _ _ E (5L)</code> or tap <b>💡 Hint</b>.\n"
            "4. Type found words in chat to score points!"
            "</blockquote>"
        )
    elif section == "scores":
        text = (
            "🏆 <b>Leaderboard &amp; Scores</b>\n\n"
            "<blockquote>"
            "• <code>/leaderboard [global|group] [today|week|month|all] [4|5|6]</code>\n"
            "• <code>/score [@user] [global|group] [today|week|month|all] [4|5|6]</code>\n"
            "• <code>/profile</code> — Combined Word Grid &amp; WordSeek card"
            "</blockquote>"
        )
    elif section == "group":
        text = (
            "⚙️ <b>Group Settings (Admin Only)</b>\n\n"
            "<blockquote>"
            "• <code>/seekauth @user</code> / <code>remove</code> / <code>list</code>\n"
            "• <code>/setgametopic</code> &amp; <code>/unsetgametopic</code>\n"
            "• <code>/allowonlylen 5 4 6</code>"
            "</blockquote>"
        )
    elif section == "other":
        text = (
            "🆔 <b>Other Commands</b>\n\n"
            "<blockquote>"
            "• <code>/id</code> — View chat, user, topic, and message IDs\n"
            "• <code>/profile</code> — View your player profile card"
            "</blockquote>"
        )
    elif section == "admin":
        text = (
            "👑 <b>Admin Commands</b>\n\n"
            "<blockquote>"
            "• <code>/panel</code>, <code>/stats</code>, <code>/broadcast</code>\n"
            "• <code>/ban [id]</code>, <code>/unban [id]</code>, <code>/transfer &lt;from&gt; &lt;to&gt;</code>"
            "</blockquote>"
        )
    else:
        text = (
            "🟩 <b>How to Play WordSeek</b>\n\n"
            "<blockquote>"
            "1. Start a game using <code>/new</code>, <code>/new4</code>, <code>/new5</code>, or <code>/new6</code>.\n"
            "2. Guess the hidden word — each letter becomes a colored button in the message:\n"
            "   🟩 <b>Green:</b> right letter, right spot\n"
            "   🟨 <b>Default:</b> right letter, wrong spot\n"
            "   🟥 <b>Red:</b> letter isn't in the word\n"
            "3. First player to guess wins! Max 30 guesses.\n"
            "4. Use <code>/daily</code> in DM for the 6-try Word of the Day!"
            "</blockquote>"
        )
    return text, pyro_markup


# ============================================================================
# SHARED START & PROFILE VIEWS
# ============================================================================
def build_start_view(
    first_name: str, bot_username: str, is_private: bool = True
) -> tuple[str, InlineKeyboardMarkup]:
    safe_name = normalize_fancy_telegram_name(first_name)
    uname = bot_username or "WordGridGameBot"

    if not is_private:
        text = (
            "🎮 <b>WordSeek &amp; Word Grid Ready!</b>\n\n"
            "<blockquote>"
            "🟩 <b>WordSeek:</b> <code>/new</code> • <code>/new4</code> • <code>/new5</code> • <code>/new6</code> • <code>/end</code>\n"
            "🧩 <b>Word Grid:</b> <code>/game</code> • <code>/hint</code> • <code>/stopgame</code>\n"
            "🏆 <b>Ranks &amp; Scores:</b> <code>/leaderboard</code> • <code>/score</code>"
            "</blockquote>"
        )
        markup = InlineKeyboardMarkup(
            [
                [
                    InlineKeyboardButton("🟩 Start Seek", callback_data="ws:new:5"),
                    InlineKeyboardButton("🧩 Start Grid", callback_data="game:new"),
                ],
                [
                    InlineKeyboardButton("🏆 Ranks", callback_data="wslb:group:all:5"),
                    InlineKeyboardButton("📖 Help", callback_data="help:howto"),
                ],
            ]
        )
        return text, markup

    text = (
        f"<b>Welcome to WordSeek &amp; Word Grid!</b>\n\n"
        f"Hey <b>{safe_name}</b>! Play competitive WordSeek (Wordle 4L/5L/6L) and 3D Word Grid directly on Telegram.\n\n"
        f"<blockquote><b>Quick Start:</b>\n"
        f"• Use <code>/new</code> (or <code>/new4</code>, <code>/new5</code>, <code>/new6</code>) to start WordSeek\n"
        f"• Use <code>/daily</code> for WordSeek of the Day (6 attempts)\n"
        f"• Use <code>/game</code> in a group for 3D Word Grid Arcade\n"
        f"• Use <code>/help</code> for detailed instructions and command list</blockquote>\n\n"
        f"Ready to test your word skills? Let's play!"
    )

    markup = InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton(
                    "➕ Add to Group",
                    url=f"https://t.me/{uname}?startgroup=true",
                )
            ],
            [
                InlineKeyboardButton("🟩 Play Seek", callback_data="ws:new:5"),
                InlineKeyboardButton("🎯 Daily", callback_data="ws:daily"),
            ],
            [
                InlineKeyboardButton("🏆 Ranks", callback_data="wslb:global:all:5"),
                InlineKeyboardButton("👤 Profile", callback_data="nav:profile"),
                InlineKeyboardButton("📖 Help", callback_data="help:howto"),
            ],
            [
                InlineKeyboardButton("📢 Updates", url=UPDATE_CHANNEL),
                InlineKeyboardButton("💬 Discussion", url=SUPPORT_GROUP),
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
        f"👤 <b>Player Profile — {safe_name}</b>\n\n"
        f"<blockquote>"
        f"🟩 <b>WordSeek Stats (5L)</b>\n"
        f"• <b>Score:</b> <code>{seek_score:,} pts</code> ({seek_rank_str})\n"
        f"• <b>Daily Streak:</b> <code>{curr_streak} days</code> (Best: <code>{high_streak} days</code>)"
        f"</blockquote>\n"
        f"<blockquote>"
        f"🧩 <b>Word Grid Arcade</b>\n"
        f"• <b>Score:</b> <code>{grid_score:,} pts</code> ({grid_rank_str})\n"
        f"• <b>Words Found:</b> <code>{words_found:,}</code>  |  <b>Best:</b> <code>Round {best_round}</code>"
        f"</blockquote>"
    )

    rows = [
        [
            InlineKeyboardButton("🔄 Refresh", callback_data="profile:refresh"),
            InlineKeyboardButton("🏆 Ranks", callback_data="wslb:global:all:5"),
        ]
    ]
    if show_back:
        rows.append([InlineKeyboardButton("⬅️ Back", callback_data="nav:home")])

    return text, InlineKeyboardMarkup(rows)


# ============================================================================
# BOT API 10.3 STYLED LEADERBOARD & SCORE KEYBOARDS (style="primary" / "success")
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
    Ported from WordSeek-master's `generate-leaderboard-keyboard.ts`.
    Sets `"style": "primary"` (Blue) on active filter buttons and `"style": "success"` (Green) on support!
    """
    rows = []

    if include_game_switch:
        rows.append(
            [
                {
                    "text": "« 🟩 WordSeek »",
                    "callback_data": f"{prefix}:{search_key}:{time_key}:{word_length}",
                    "style": "primary",
                },
                {
                    "text": "🧩 Word Grid",
                    "callback_data": "lb:users",
                },
            ]
        )

    # Scope row: Global | 🔄 | This chat
    g_btn = {
        "text": _fmt_tab("Global", search_key == "global"),
        "callback_data": f"{prefix}:global:{time_key}:{word_length}",
    }
    if search_key == "global":
        g_btn["style"] = "primary"

    c_btn = {
        "text": _fmt_tab("This chat", search_key == "group"),
        "callback_data": f"{prefix}:group:{time_key}:{word_length}",
    }
    if search_key == "group":
        c_btn["style"] = "primary"

    rows.append(
        [
            g_btn,
            {
                "text": "🔄",
                "callback_data": f"{prefix}:{search_key}:{time_key}:{word_length}:r",
            },
            c_btn,
        ]
    )

    # Time period rows (3 per row, just like generate-leaderboard-keyboard.ts)
    time_items = [
        ("today", "Today"),
        ("week", "This week"),
        ("month", "This month"),
        ("year", "This year"),
        ("all", "All time"),
    ]
    t_row = []
    for t_k, t_label in time_items:
        b = {
            "text": _fmt_tab(t_label, time_key == t_k),
            "callback_data": f"{prefix}:{search_key}:{t_k}:{word_length}",
        }
        if time_key == t_k:
            b["style"] = "primary"
        t_row.append(b)
        if len(t_row) == 3:
            rows.append(t_row)
            t_row = []
    if t_row:
        rows.append(t_row)

    # Word length row: 4 letters | 5 letters | 6 letters
    len_row = []
    for ln in (4, 5, 6):
        b = {
            "text": _fmt_tab(f"{ln} letters", word_length == ln),
            "callback_data": f"{prefix}:{search_key}:{time_key}:{ln}",
        }
        if word_length == ln:
            b["style"] = "primary"
        len_row.append(b)
    rows.append(len_row)

    rows.append(
        [
            {"text": "📢 Updates", "url": UPDATE_CHANNEL},
            {"text": "💬 Discussion", "url": SUPPORT_GROUP, "style": "success"},
        ]
    )

    if show_back:
        rows.append([{"text": "⬅️ Back", "callback_data": "nav:home"}])

    return {"inline_keyboard": rows}


def build_seek_score_view(
    score_data: dict | None,
    target_id: int,
    target_name: str,
    search_key: str = "global",
    time_key: str = "all",
    word_length: int = 5,
) -> tuple[str, InlineKeyboardMarkup, dict]:
    """
    Ported from WordSeek's `formatUserScoreMessage` + `generateLeaderboardKeyboard`.
    Returns `(text_html, pyrogram_markup, bot_api_styled_markup_dict)`.
    """
    safe_name = normalize_fancy_telegram_name((score_data or {}).get("name") or target_name)
    uname = (score_data or {}).get("username")
    mention = f'<a href="https://t.me/{uname}">{safe_name}</a>' if uname else safe_name
    scope_text = "globally" if search_key == "global" else "in this chat"

    if not score_data or (score_data.get("total_score", 0) == 0 and score_data.get("highest_streak", 0) == 0):
        text = (
            f"<blockquote><strong>🏆 Regular WordSeek Scores ({word_length}L)</strong></blockquote>\n"
            f"<b>{mention}</b> has no scores recorded {scope_text} for this period yet.\n\n"
            f"<i>Start a game with <code>/new{word_length}</code> or play <code>/daily</code>!</i>"
        )
    else:
        tot = score_data.get("total_score", 0)
        rnk = score_data.get("rank", 0)
        c_str = score_data.get("current_streak", 0)
        h_str = score_data.get("highest_streak", 0)
        text = (
            f"<blockquote><strong>🏆 Regular WordSeek Scores</strong></blockquote>\n"
            f"<b>{mention}</b> has a total score of <b>{tot:,}</b> {scope_text}.\n"
            f"Their rank is <b>#{rnk:,}</b>.\n\n"
            f"<blockquote><strong>🔥 Daily WordSeek Stats</strong></blockquote>\n"
            f"<b>Current Streak:</b> {c_str} days\n"
            f"<b>Highest Streak:</b> {h_str} days"
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
    """
    Ported from WordSeek's `formatLeaderboardMessage` + `generateLeaderboardKeyboard`.
    Returns `(text_html, pyrogram_markup, bot_api_styled_markup_dict)`.
    """
    scope_title = "Global" if search_key == "global" else "Group"
    header = f"<blockquote>🏆 {scope_title} Leaderboard 🏆</blockquote>\n\n"

    if not entries:
        body = f"<blockquote>No scores recorded yet! Start a game with <code>/new{word_length}</code>.</blockquote>"
    else:
        blocks: list[list[str]] = []
        for index, entry in enumerate(entries[:20]):
            rank_icon = ["🥇", "🥈", "🥉"][index] if index < 3 else "🔅"
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

            line = f"{rank_icon}{user_link} - {pts:,} pts"
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
    medals = {0: "🥇", 1: "🥈", 2: "🥉"}

    if mode == "groups":
        header = "<blockquote>🏆 <b>Word Grid — Top Groups</b></blockquote>\n\n"
        if not entries:
            body = "<blockquote>No groups have scored yet! Send <code>/game</code> in your group.</blockquote>"
        else:
            lines = []
            for idx, g in enumerate(entries[:10]):
                badge = medals.get(idx, "🔅")
                title = normalize_fancy_telegram_name(g.get("title", "Group"), max_len=24)
                score = g.get("score", 0)
                best_r = g.get("best_round", 1)
                lines.append(f"{badge} <b>{title}</b> - {score:,} pts <i>(R{best_r})</i>")
            body = "<blockquote>" + "\n".join(lines) + "</blockquote>"

        tabs = [
            InlineKeyboardButton("👤 Players", callback_data="lb:users"),
            InlineKeyboardButton("« 👥 Groups »", callback_data="lb:groups"),
        ]
        refresh_cb = "lb:refresh:groups"
    else:
        header = "<blockquote>🏆 <b>Word Grid — Top Players</b></blockquote>\n\n"
        if not entries:
            body = "<blockquote>No players have scored yet! Send <code>/game</code> to play.</blockquote>"
        else:
            lines = []
            for idx, u in enumerate(entries[:10]):
                badge = medals.get(idx, "🔅")
                name = normalize_fancy_telegram_name(u.get("first_name", "Player"), max_len=22)
                uid = u.get("user_id", 0)
                score = u.get("score", 0)
                user_link = f'<a href="tg://user?id={uid}">{name}</a>' if uid else f"<b>{name}</b>"
                lines.append(f"{badge} {user_link} - {score:,} pts")
            body = "<blockquote>" + "\n".join(lines) + "</blockquote>"

        tabs = [
            InlineKeyboardButton("« 👤 Players »", callback_data="lb:users"),
            InlineKeyboardButton("👥 Groups", callback_data="lb:groups"),
        ]
        refresh_cb = "lb:refresh:users"

    rows = [
        [
            InlineKeyboardButton("🟩 WordSeek", callback_data="wslb:global:all:5"),
            InlineKeyboardButton("« 🧩 Word Grid »", callback_data="lb:users"),
        ],
        tabs,
        [
            InlineKeyboardButton("🔄 Refresh", callback_data=refresh_cb),
            InlineKeyboardButton("👤 Profile", callback_data="nav:profile"),
        ],
    ]
    if show_back:
        rows.append([InlineKeyboardButton("⬅️ Back", callback_data="nav:home")])

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
            "📊 <b>Bot Live Statistics</b>\n\n"
            "<blockquote>"
            f"👤 <b>Total Users:</b> <code>{total_users:,}</code>\n"
            f"👥 <b>Total Groups:</b> <code>{total_groups:,}</code>\n"
            f"🧩 <b>Active Grid Games:</b> <code>{active_grid_games}</code>\n"
            f"🟩 <b>Active Seek Games:</b> <code>{active_seek_games}</code>"
            "</blockquote>\n"
            "⚡ <i>Motor pool &amp; TTL cache healthy.</i>"
        )
        markup = InlineKeyboardMarkup(
            [
                [
                    InlineKeyboardButton("🔄 Refresh", callback_data="admin:stats"),
                    InlineKeyboardButton("⬅️ Back", callback_data="admin:home"),
                ]
            ]
        )
        return text, markup

    if section == "broadcast":
        text = (
            "📢 <b>Admin Broadcast</b>\n\n"
            "<blockquote>"
            "Reply to any message with <code>/broadcast</code> to send it to all users and groups with FloodWait protection.\n\n"
            "<b>Other Owner Commands:</b>\n"
            "• <code>/stats</code> — Detailed system &amp; RAM metrics\n"
            "• <code>/ban [user_id]</code> &amp; <code>/unban [user_id]</code>\n"
            "• <code>/transfer &lt;from_id&gt; &lt;to_id&gt;</code>"
            "</blockquote>"
        )
        markup = InlineKeyboardMarkup(
            [[InlineKeyboardButton("⬅️ Back", callback_data="admin:home")]]
        )
        return text, markup

    text = (
        "🛠 <b>Admin Control Panel</b>\n\n"
        "<blockquote>"
        "Manage Word Grid Arcade &amp; WordSeek statistics, active games, user moderation, and broadcasts."
        "</blockquote>"
    )
    markup = InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton("📊 Stats", callback_data="admin:stats"),
                InlineKeyboardButton("📢 Broadcast", callback_data="admin:broadcast"),
            ]
        ]
    )
    return text, markup
