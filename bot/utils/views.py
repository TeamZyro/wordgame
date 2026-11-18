import html
import unicodedata
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from bot.config import SUPPORT_GROUP, UPDATE_CHANNEL


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
    """Compact inline buttons for the Word Grid board (short labels so text never overflows)."""
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
# WORDSEEK BOARD VIEW & COMPACT LETTER BUTTONS
# ============================================================================
def build_wordseek_board_view(
    guesses: list[str],
    solution: str,
    max_guesses: int = 30,
    evaluate_fn=None,
    format_row_fn=None,
) -> tuple[str, InlineKeyboardMarkup]:
    """
    Builds the WordSeek board message (HTML) + interactive letter hint buttons.
    Each button uses a short 2-char label (`🟩S`, `🟨T`, `🟥A`) so 4/5/6 buttons per row fit cleanly.
    """
    word_len = len(solution)
    rows_html = []
    if format_row_fn:
        for g in guesses:
            rows_html.append(format_row_fn(g, solution))

    text = (
        f"🟩 <b>WordSeek — {word_len}-Letter Mode</b>  (<i>{len(guesses)}/{max_guesses} guesses</i>)\n"
        f"<blockquote>" + ("\n".join(rows_html) if rows_html else "Type a word to guess!") + "</blockquote>\n"
        f"<i>Tap any letter button below to see its color hint, or type a {word_len}-letter word!</i>"
    )

    kb_rows = []
    # Show interactive letter buttons for the latest 5 guesses so the keyboard stays compact
    recent_guesses = guesses[-5:]
    state_icon = {"correct": "🟩", "present": "🟨", "absent": "🟥"}
    if evaluate_fn:
        for g in recent_guesses:
            states = evaluate_fn(g, solution)
            btn_row = []
            for idx, ch in enumerate(g.upper()):
                st = states[idx]
                icon = state_icon.get(st, "🟥")
                btn_row.append(
                    InlineKeyboardButton(
                        f"{icon}{ch}",
                        callback_data=f"wh:{st}:{ch}",
                    )
                )
            kb_rows.append(btn_row)

    kb_rows.append(
        [
            InlineKeyboardButton("💡 Hint", callback_data="ws:hint"),
            InlineKeyboardButton("🛑 End", callback_data="ws:end"),
        ]
    )
    return text, InlineKeyboardMarkup(kb_rows)


# ============================================================================
# SHARED START, HELP, PROFILE, SCORE & LEADERBOARD VIEWS (@tgbot Rule 5)
# ============================================================================
def build_start_view(
    first_name: str, bot_username: str, is_private: bool = True
) -> tuple[str, InlineKeyboardMarkup]:
    """Single Source of Truth view builder for `/start` and `nav:home`."""
    safe_name = normalize_fancy_telegram_name(first_name)
    uname = bot_username or "WordGridGameBot"

    if not is_private:
        text = (
            "🎮 <b>Word Arcade &amp; WordSeek Ready!</b>\n\n"
            "<blockquote>"
            "🧩 <b>Word Grid (3D Search):</b> <code>/game</code>  •  <code>/stopgame</code>  •  <code>/hint</code>\n"
            "🟩 <b>WordSeek (Wordle 4/5/6L):</b> <code>/new</code>  •  <code>/new4</code>  •  <code>/new5</code>  •  <code>/new6</code>  •  <code>/end</code>\n"
            "🏆 <b>Stats &amp; Ranks:</b> <code>/score</code>  •  <code>/profile</code>  •  <code>/leaderboard</code>"
            "</blockquote>\n"
            "⚡ <i>Tap a game mode below to start playing!</i>"
        )
        markup = InlineKeyboardMarkup(
            [
                [
                    InlineKeyboardButton("🧩 Start Grid", callback_data="game:new"),
                    InlineKeyboardButton("🟩 Start Seek", callback_data="ws:new:5"),
                ],
                [
                    InlineKeyboardButton("🏆 Ranks", callback_data="nav:lb"),
                    InlineKeyboardButton("📖 Help", callback_data="help:howto"),
                ],
            ]
        )
        return text, markup

    text = (
        f"🎮 <b>Welcome to Word Grid &amp; WordSeek!</b>\n\n"
        f"Hey <b>{safe_name}</b>! Play <b>two complete word games</b> in one bot:\n\n"
        f"<blockquote>"
        f"🧩 <b>1. Word Grid Arcade (3D Word Search)</b>\n"
        f"• <code>/game</code> — Start 3D Grid Round in groups\n"
        f"• <code>/hint</code> — Reveal a letter  |  <code>/stopgame</code> — Stop\n\n"
        f"🟩 <b>2. WordSeek (Wordle 4, 5 &amp; 6 Letters)</b>\n"
        f"• <code>/new</code> or <code>/wordseek</code> — Start 5L WordSeek\n"
        f"• <code>/new4</code> <code>/new5</code> <code>/new6</code> — Pick word length\n"
        f"• <code>/daily</code> — Daily WordSeek (DM)  |  <code>/end</code> — End game\n\n"
        f"🏆 <b>Ranks &amp; Stats:</b> <code>/score</code>  •  <code>/profile</code>  •  <code>/leaderboard</code>"
        f"</blockquote>"
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
                InlineKeyboardButton("🏆 Ranks", callback_data="nav:lb"),
                InlineKeyboardButton("👤 Profile", callback_data="nav:profile"),
                InlineKeyboardButton("📖 Help", callback_data="help:howto"),
            ],
            [
                InlineKeyboardButton("💬 Support", url=SUPPORT_GROUP),
                InlineKeyboardButton("📢 Channel", url=UPDATE_CHANNEL),
            ],
        ]
    )
    return text, markup


def _fmt_tab(label: str, active: bool) -> str:
    return f"« {label} »" if active else label


def build_help_view(
    bot_username: str,
    section: str = "howto",
    is_admin: bool = False,
    show_back: bool = True,
) -> tuple[str, InlineKeyboardMarkup]:
    """
    Single Source of Truth tabbed Help builder for `/help` and `help:*` / `nav:help` callbacks.
    Covers both WordSeek and Word Grid Arcade with compact tab buttons.
    """
    uname = bot_username or "WordGridGameBot"

    if section == "grid":
        text = (
            "🧩 <b>How to Play Word Grid Arcade</b>\n\n"
            "<blockquote>"
            "1. Send <code>/game</code> in a group chat to start Round 1.\n"
            "2. Find hidden words horizontally (→), vertically (↓), or diagonally (↘ ↙).\n"
            "3. Check the caption for letter hints like <code>A _ _ _ E (5L)</code> or tap <b>💡 Hint</b>.\n"
            "4. Type found words in chat to score points!\n"
            "5. Clear all words before the timer ends to advance to the next round."
            "</blockquote>\n\n"
            "⭐ <b>Grid Scoring:</b>\n"
            "• <b>3–4L:</b> <code>+1 pt</code>  |  <b>5–6L:</b> <code>+2 pts</code>  |  <b>7–8L:</b> <code>+3 pts</code> (+1 bonus every 10 rounds)"
        )
    elif section == "scores":
        text = (
            "🏆 <b>Leaderboards &amp; Scores Guide</b>\n\n"
            "<blockquote>"
            "• <code>/leaderboard</code> — Open interactive Dual Leaderboard\n"
            "• <code>/leaderboard global week 5</code> — Filter WordSeek ranks\n"
            "• <code>/score</code> — View your WordSeek &amp; Daily streak stats\n"
            "• <code>/score @username global all 5</code> — Inspect a player's score\n"
            "• <code>/profile</code> or <code>/rank</code> — View combined player card"
            "</blockquote>\n\n"
            "📊 <b>Filter Options:</b>\n"
            "• <b>Scope:</b> <code>group</code>, <code>global</code>\n"
            "• <b>Period:</b> <code>today</code>, <code>week</code>, <code>month</code>, <code>year</code>, <code>all</code>\n"
            "• <b>Length:</b> <code>4</code>, <code>5</code>, <code>6</code>"
        )
    elif section == "group":
        text = (
            "⚙️ <b>Group &amp; Topic Settings (Admins)</b>\n\n"
            "<blockquote>"
            "🔐 <b>Authorized Users:</b>\n"
            "• <code>/seekauth @user</code> — Allow user to end WordSeek without voting\n"
            "• <code>/seekauth remove @user</code> — Remove user\n"
            "• <code>/seekauth list</code> — View authorized users\n\n"
            "📌 <b>Forum Topics:</b>\n"
            "• <code>/setgametopic</code> — Restrict games to current forum topic\n"
            "• <code>/unsetgametopic</code> — Remove topic restriction\n"
            "• <code>/allowonlylen 5 4 6</code> — Set allowed WordSeek lengths\n\n"
            "🆔 <b>Utility:</b>\n"
            "• <code>/id</code> — View chat, user, and replied message IDs"
            "</blockquote>"
        )
    elif section == "admin":
        text = (
            "👑 <b>Bot Owner Commands (Sudo Only)</b>\n\n"
            "<blockquote>"
            "• <code>/panel</code> or <code>/admin</code> — Open Admin Control Panel\n"
            "• <code>/stats</code> — Live system, RAM, and database statistics\n"
            "• <code>/broadcast</code> — Reply to any message to broadcast\n"
            "• <code>/ban [user_id]</code> — Ban a user globally\n"
            "• <code>/unban [user_id]</code> — Unban a user\n"
            "• <code>/transfer &lt;from_id&gt; &lt;to_id&gt;</code> — Transfer WordSeek scores"
            "</blockquote>"
        )
    else:
        section = "howto"
        text = (
            "🟩 <b>How to Play WordSeek</b>\n\n"
            "<blockquote>"
            "1. Start a game with <code>/new</code>, <code>/wordseek</code>, <code>/new4</code>, <code>/new5</code>, or <code>/new6</code>.\n"
            "2. Type a valid 4, 5, or 6-letter word to guess.\n"
            "3. Color feedback after every guess:\n"
            "   🟩 <b>Green:</b> Right letter in the right spot\n"
            "   🟨 <b>Yellow:</b> Right letter in the wrong spot\n"
            "   🟥 <b>Red:</b> Letter is not in the word\n"
            "4. First player to guess the secret word wins <code>(30 - guesses)</code> pts!\n"
            "5. Use <code>/daily</code> in private chat for the 6-try Word of the Day!"
            "</blockquote>\n\n"
            "💡 <i>Switch tabs below for <b>🧩 Word Grid</b>, <b>🏆 Scores</b>, and <b>⚙️ Group</b> rules!</i>"
        )

    rows = [
        [
            InlineKeyboardButton(_fmt_tab("🟩 Seek", section == "howto"), callback_data="help:howto"),
            InlineKeyboardButton(_fmt_tab("🧩 Grid", section == "grid"), callback_data="help:grid"),
        ],
        [
            InlineKeyboardButton(_fmt_tab("🏆 Scores", section == "scores"), callback_data="help:scores"),
            InlineKeyboardButton(_fmt_tab("⚙️ Group", section == "group"), callback_data="help:group"),
        ],
    ]
    if is_admin:
        rows.append(
            [InlineKeyboardButton(_fmt_tab("👑 Admin", section == "admin"), callback_data="help:admin")]
        )
    rows.append(
        [
            InlineKeyboardButton("➕ Add Bot", url=f"https://t.me/{uname}?startgroup=true"),
            InlineKeyboardButton("💬 Support", url=SUPPORT_GROUP),
        ]
    )
    if show_back:
        rows.append([InlineKeyboardButton("⬅️ Back", callback_data="nav:home")])

    return text, InlineKeyboardMarkup(rows)


def build_profile_view(
    user_id: int,
    first_name: str,
    user_doc: dict | None,
    rank: int,
    seek_data: dict | None = None,
    show_back: bool = True,
) -> tuple[str, InlineKeyboardMarkup]:
    """Unified Player Profile Card showing both Word Grid Arcade & WordSeek stats."""
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

    total_combined = grid_score + seek_score
    if total_combined >= 1000:
        tier = "👑 Grand Word Legend"
    elif total_combined >= 400:
        tier = "💎 Word Grandmaster"
    elif total_combined >= 150:
        tier = "🔥 Puzzle Master"
    elif total_combined >= 40:
        tier = "⚡ Word Hunter"
    else:
        tier = "🌱 Arcade Rookie"

    text = (
        f"👤 <b>Player Profile — {safe_name}</b>\n"
        f"🎖 <b>Rank Title:</b> <code>{tier}</code>\n\n"
        f"<blockquote>"
        f"🧩 <b>Word Grid Arcade</b>\n"
        f"• <b>Score:</b> <code>{grid_score:,} pts</code> ({grid_rank_str})\n"
        f"• <b>Words Found:</b> <code>{words_found:,}</code>  |  <b>Best:</b> <code>R{best_round}</code>"
        f"</blockquote>\n"
        f"<blockquote>"
        f"🟩 <b>WordSeek (Wordle)</b>\n"
        f"• <b>Score (5L):</b> <code>{seek_score:,} pts</code> ({seek_rank_str})\n"
        f"• <b>Daily Streak:</b> <code>{curr_streak}d</code> (Best: <code>{high_streak}d</code>)"
        f"</blockquote>"
    )

    rows = [
        [
            InlineKeyboardButton("🔄 Refresh", callback_data="profile:refresh"),
            InlineKeyboardButton("🏆 Ranks", callback_data="nav:lb"),
        ]
    ]
    if show_back:
        rows.append([InlineKeyboardButton("⬅️ Back", callback_data="nav:home")])

    return text, InlineKeyboardMarkup(rows)


def build_seek_score_view(
    score_data: dict | None,
    target_id: int,
    target_name: str,
    search_key: str = "global",
    time_key: str = "all",
    word_length: int = 5,
) -> tuple[str, InlineKeyboardMarkup]:
    """
    Ported from WordSeek's `formatUserScoreMessage` + `generateLeaderboardKeyboard`
    with compact button labels.
    """
    safe_name = normalize_fancy_telegram_name((score_data or {}).get("name") or target_name)
    scope_label = "globally" if search_key == "global" else "in this chat"
    time_labels = {
        "today": "Today",
        "week": "This Week",
        "month": "This Month",
        "year": "This Year",
        "all": "All Time",
    }
    period_label = time_labels.get(time_key, "All Time")

    if not score_data or (score_data.get("total_score", 0) == 0 and score_data.get("highest_streak", 0) == 0):
        text = (
            f"<blockquote>📊 <b>WordSeek Score ({word_length}L • {period_label})</b></blockquote>\n"
            f"<b>{safe_name}</b> has no recorded {word_length}-letter WordSeek scores {scope_label} for <b>{period_label}</b> yet.\n\n"
            f"<i>Start a round with <code>/new{word_length}</code> or play <code>/daily</code>!</i>"
        )
    else:
        tot = score_data.get("total_score", 0)
        rnk = score_data.get("rank", 0)
        c_str = score_data.get("current_streak", 0)
        h_str = score_data.get("highest_streak", 0)
        rnk_txt = f"<b>#{rnk:,}</b>" if rnk > 0 else "<b>Unranked</b>"
        text = (
            f"<blockquote>🏆 <b>WordSeek Scores ({word_length}L • {period_label})</b></blockquote>\n"
            f"<b>{safe_name}</b> has a total score of <b>{tot:,} pts</b> {scope_label}.\n"
            f"Rank: {rnk_txt}\n\n"
            f"<blockquote>🔥 <b>Daily WordSeek Streak</b>\n"
            f"• <b>Current Streak:</b> <code>{c_str} days</code>\n"
            f"• <b>Highest Streak:</b> <code>{h_str} days</code></blockquote>"
        )

    prefix = f"wsscore:{target_id}"
    markup = build_seek_filter_keyboard(search_key, time_key, word_length, prefix=prefix)
    return text, markup


def build_seek_filter_keyboard(
    search_key: str,
    time_key: str,
    word_length: int,
    prefix: str = "wslb",
    include_game_switch: bool = False,
    show_back: bool = False,
) -> InlineKeyboardMarkup:
    """Compact filter keyboard for WordSeek Leaderboards and `/score` views."""
    rows = []
    if include_game_switch:
        rows.append(
            [
                InlineKeyboardButton("🟩 WordSeek ✅", callback_data=f"{prefix}:{search_key}:{time_key}:{word_length}"),
                InlineKeyboardButton("🧩 Word Grid", callback_data="lb:users"),
            ]
        )

    rows.append(
        [
            InlineKeyboardButton(
                _fmt_tab("Global", search_key == "global"),
                callback_data=f"{prefix}:global:{time_key}:{word_length}",
            ),
            InlineKeyboardButton(
                "🔄",
                callback_data=f"{prefix}:{search_key}:{time_key}:{word_length}:r",
            ),
            InlineKeyboardButton(
                _fmt_tab("Chat", search_key == "group"),
                callback_data=f"{prefix}:group:{time_key}:{word_length}",
            ),
        ]
    )

    rows.append(
        [
            InlineKeyboardButton(
                _fmt_tab("Today", time_key == "today"),
                callback_data=f"{prefix}:{search_key}:today:{word_length}",
            ),
            InlineKeyboardButton(
                _fmt_tab("Week", time_key == "week"),
                callback_data=f"{prefix}:{search_key}:week:{word_length}",
            ),
            InlineKeyboardButton(
                _fmt_tab("Month", time_key == "month"),
                callback_data=f"{prefix}:{search_key}:month:{word_length}",
            ),
        ]
    )

    rows.append(
        [
            InlineKeyboardButton(
                _fmt_tab("Year", time_key == "year"),
                callback_data=f"{prefix}:{search_key}:year:{word_length}",
            ),
            InlineKeyboardButton(
                _fmt_tab("All Time", time_key == "all"),
                callback_data=f"{prefix}:{search_key}:all:{word_length}",
            ),
        ]
    )

    rows.append(
        [
            InlineKeyboardButton(
                _fmt_tab("4L", word_length == 4),
                callback_data=f"{prefix}:{search_key}:{time_key}:4",
            ),
            InlineKeyboardButton(
                _fmt_tab("5L", word_length == 5),
                callback_data=f"{prefix}:{search_key}:{time_key}:5",
            ),
            InlineKeyboardButton(
                _fmt_tab("6L", word_length == 6),
                callback_data=f"{prefix}:{search_key}:{time_key}:6",
            ),
        ]
    )

    if show_back:
        rows.append([InlineKeyboardButton("⬅️ Back", callback_data="nav:home")])

    return InlineKeyboardMarkup(rows)


def build_seek_leaderboard_view(
    entries: list[dict],
    search_key: str = "global",
    time_key: str = "all",
    word_length: int = 5,
    show_back: bool = False,
) -> tuple[str, InlineKeyboardMarkup]:
    """Formats WordSeek Leaderboard matching `format-leaderboard-message.ts` with Dual Game tabs."""
    scope_title = "Global" if search_key == "global" else "Chat"
    time_map = {"today": "Today", "week": "Week", "month": "Month", "year": "Year", "all": "All Time"}
    t_label = time_map.get(time_key, "All Time")

    header = f"<blockquote>🏆 <b>WordSeek {scope_title} Leaderboard ({word_length}L • {t_label})</b></blockquote>\n\n"
    if not entries:
        body = f"<blockquote>No {word_length}-letter WordSeek scores recorded for this filter yet!\nStart playing with <code>/new{word_length}</code>.</blockquote>"
    else:
        medals = {0: "🥇", 1: "🥈", 2: "🥉"}
        lines = []
        for idx, row in enumerate(entries[:15]):
            badge = medals.get(idx, f"<b>{idx + 1}.</b>")
            name = normalize_fancy_telegram_name(row.get("name", "Player"), max_len=22)
            uid = row.get("user_id", 0)
            pts = row.get("total_score", 0)
            link = f'<a href="tg://user?id={uid}">{name}</a>' if uid else f"<b>{name}</b>"
            lines.append(f"{badge} {link} — <code>{pts:,} pts</code>")
        body = "<blockquote>" + "\n".join(lines) + "</blockquote>"

    markup = build_seek_filter_keyboard(
        search_key=search_key,
        time_key=time_key,
        word_length=word_length,
        prefix="wslb",
        include_game_switch=True,
        show_back=show_back,
    )
    return header + body, markup


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
                badge = medals.get(idx, f"<b>{idx + 1}.</b>")
                title = normalize_fancy_telegram_name(g.get("title", "Group"), max_len=24)
                score = g.get("score", 0)
                best_r = g.get("best_round", 1)
                lines.append(f"{badge} <b>{title}</b> — <code>{score:,} pts</code> <i>(R{best_r})</i>")
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
                badge = medals.get(idx, f"<b>{idx + 1}.</b>")
                name = normalize_fancy_telegram_name(u.get("first_name", "Player"), max_len=22)
                uid = u.get("user_id", 0)
                score = u.get("score", 0)
                user_link = f'<a href="tg://user?id={uid}">{name}</a>' if uid else f"<b>{name}</b>"
                lines.append(f"{badge} {user_link} — <code>{score:,} pts</code>")
            body = "<blockquote>" + "\n".join(lines) + "</blockquote>"

        tabs = [
            InlineKeyboardButton("« 👤 Players »", callback_data="lb:users"),
            InlineKeyboardButton("👥 Groups", callback_data="lb:groups"),
        ]
        refresh_cb = "lb:refresh:users"

    rows = [
        [
            InlineKeyboardButton("🟩 WordSeek", callback_data="wslb:global:all:5"),
            InlineKeyboardButton("🧩 Word Grid ✅", callback_data="lb:users"),
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
    """Single Source of Truth view builder for `/panel`, `/admin`, and `admin:*` callbacks."""
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
