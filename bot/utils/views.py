import html
import unicodedata
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from bot.config import SUPPORT_GROUP, UPDATE_CHANNEL


def normalize_fancy_telegram_name(name: str | None, max_len: int = 28) -> str:
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
    """
    Creates a clean, single-spaced hint pattern for a word.
    - 3 letters: first & last letter shown (`C _ T`)
    - 4-5 letters: first & last letter shown (`G _ _ E`, `A _ _ _ E`)
    - 6-8 letters: first, middle, & last letter shown (`P _ Z _ L E`)
    Plus any indices unlocked via `/hint`.
    """
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


def build_game_caption(game_data: dict, status_banner: str | None = None) -> str:
    """Builds the HTML caption for the active or completed Word Grid board."""
    round_num = game_data.get("round", 1)
    time_limit = game_data.get("time_limit", 60)
    theme_name = str(game_data.get("theme", "emerald")).upper()
    words_dict = game_data.get("words", {})
    total_words = len(words_dict)
    found_count = sum(1 for info in words_dict.values() if info.get("found_by"))
    hints_used = game_data.get("hints_used", 0)
    max_hints = game_data.get("max_hints", 3)

    lines = [
        f"🧩 <b>WORD GRID ARCADE — ROUND {round_num}</b>",
        f"🎨 <b>Theme:</b> <code>{theme_name}</code>  •  ⏱ <b>Time:</b> <code>{time_limit}s</code>  •  🎯 <b>Found:</b> <code>{found_count}/{total_words}</code>",
        "",
    ]

    word_lines = []
    for actual_word, info in words_dict.items():
        finder = info.get("found_by")
        if finder:
            safe_finder = normalize_fancy_telegram_name(finder, max_len=20)
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
            f"\n💬 <i>Type a hidden word in chat!</i>  |  💡 <b>Hints:</b> <code>{max_hints - hints_used}/{max_hints}</code>"
        )

    return "\n".join(lines)


def build_game_board_markup(solved: bool = False) -> InlineKeyboardMarkup | None:
    """Inline controls attached directly to the active puzzle board."""
    if solved:
        return InlineKeyboardMarkup(
            [
                [
                    InlineKeyboardButton("▶️ Next / New Game", callback_data="game:new"),
                    InlineKeyboardButton("🏆 Leaderboard", callback_data="lb:users"),
                ]
            ]
        )
    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton("💡 Hint", callback_data="game:hint"),
                InlineKeyboardButton("🔄 Refresh Board", callback_data="game:refresh"),
            ],
            [
                InlineKeyboardButton("🛑 Stop Game", callback_data="game:stop"),
                InlineKeyboardButton("🏆 Ranks", callback_data="lb:users"),
            ],
        ]
    )


def build_start_view(
    first_name: str, bot_username: str, is_private: bool = True
) -> tuple[str, InlineKeyboardMarkup]:
    """
    Single Source of Truth view builder for `/start` and `nav:home` callback.
    """
    safe_name = normalize_fancy_telegram_name(first_name)
    uname = bot_username or "WordGridGameBot"

    if not is_private:
        text = (
            "🧩 <b>Word Grid Arcade is Ready!</b>\n\n"
            "<blockquote>"
            "🎮 <b>Start Round:</b> <code>/game</code>\n"
            "💡 <b>Get a Hint:</b> <code>/hint</code>\n"
            "🛑 <b>Stop Session:</b> <code>/stopgame</code>\n"
            "🏆 <b>Leaderboard:</b> <code>/leaderboard</code>\n"
            "👤 <b>Your Stats:</b> <code>/profile</code>"
            "</blockquote>\n"
            "⚡ <i>Tap below or type <code>/game</code> to launch Round 1!</i>"
        )
        markup = InlineKeyboardMarkup(
            [
                [
                    InlineKeyboardButton("🎮 Start Game", callback_data="game:new"),
                    InlineKeyboardButton("🏆 Leaderboard", callback_data="lb:users"),
                ],
                [
                    InlineKeyboardButton("📖 How to Play", callback_data="nav:help"),
                    InlineKeyboardButton("💬 Support", url=SUPPORT_GROUP),
                ],
            ]
        )
        return text, markup

    text = (
        f"🧩 <b>Welcome to Word Grid Arcade!</b>\n\n"
        f"Hey <b>{safe_name}</b>! I am a fast-paced <b>3D Word Search Arcade Bot</b> for Telegram groups. "
        f"Compete with friends across infinite rounds that scale in grid size and difficulty!\n\n"
        f"<blockquote>"
        f"🎮 <code>/game</code> — Start an Arcade Puzzle\n"
        f"💡 <code>/hint</code> — Reveal a Letter Hint\n"
        f"🛑 <code>/stopgame</code> — End Active Session\n"
        f"👤 <code>/profile</code> — View Your Player Card\n"
        f"🏆 <code>/leaderboard</code> — Global Rankings\n"
        f"📖 <code>/help</code> — Game Rules & Scoring"
        f"</blockquote>\n"
        f"🚀 <i>Add me to your group and send <code>/game</code> to play!</i>"
    )

    markup = InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton(
                    "➕ Add Me to Your Group ➕",
                    url=f"https://t.me/{uname}?startgroup=true",
                )
            ],
            [
                InlineKeyboardButton("🏆 Leaderboard", callback_data="nav:lb"),
                InlineKeyboardButton("👤 My Profile", callback_data="nav:profile"),
            ],
            [
                InlineKeyboardButton("📖 How to Play", callback_data="nav:help"),
            ],
            [
                InlineKeyboardButton("💬 Support GC", url=SUPPORT_GROUP),
                InlineKeyboardButton("📢 Updates", url=UPDATE_CHANNEL),
            ],
        ]
    )
    return text, markup


def build_help_view(bot_username: str, show_back: bool = True) -> tuple[str, InlineKeyboardMarkup]:
    """
    Single Source of Truth view builder for `/help` and `nav:help` callback.
    """
    uname = bot_username or "WordGridGameBot"
    text = (
        "📖 <b>Word Grid Arcade — How to Play</b>\n\n"
        "<blockquote>"
        "<b>1. Start a Match:</b> Send <code>/game</code> in any group chat to launch Round 1.\n"
        "<b>2. Scan the 3D Grid:</b> Words are hidden horizontally (→), vertically (↓), or diagonally (↘ ↙).\n"
        "<b>3. Use the Hints:</b> Check the board caption for letter hints like <code>A _ _ _ E (5L)</code> or tap <b>💡 Hint</b>.\n"
        "<b>4. Type to Score:</b> Simply type the word in chat! First player to find it earns points.\n"
        "<b>5. Advance Rounds:</b> Find all words before the timer runs out to auto-advance to the next harder round!\n"
        "<b>6. Timeout Reset:</b> If the timer expires, the streak resets back to Round 1."
        "</blockquote>\n\n"
        "⭐ <b>Scoring System:</b>\n"
        "• <b>3–4 Letter Words:</b> <code>+1 pt</code> (+ Round Bonus)\n"
        "• <b>5–6 Letter Words:</b> <code>+2 pts</code> (+ Round Bonus)\n"
        "• <b>7–8 Letter Words:</b> <code>+3 pts</code> (+ Round Bonus)\n"
        "• <b>Streak Bonus:</b> <code>+1 extra pt</code> every 10 rounds!"
    )

    buttons = [
        [
            InlineKeyboardButton(
                "➕ Add to Group", url=f"https://t.me/{uname}?startgroup=true"
            ),
            InlineKeyboardButton("💬 Support GC", url=SUPPORT_GROUP),
        ]
    ]
    if show_back:
        buttons.append([InlineKeyboardButton("⬅️ Back to Home", callback_data="nav:home")])

    return text, InlineKeyboardMarkup(buttons)


def build_profile_view(
    user_id: int,
    first_name: str,
    user_doc: dict | None,
    rank: int,
    show_back: bool = True,
) -> tuple[str, InlineKeyboardMarkup]:
    """
    Single Source of Truth view builder for `/profile`, `/rank`, `/stats`, and `nav:profile` / `profile:refresh`.
    """
    safe_name = normalize_fancy_telegram_name(first_name)
    score = (user_doc or {}).get("score", 0)
    games_played = (user_doc or {}).get("games_played", 0)
    words_found = (user_doc or {}).get("words_found", games_played)
    best_round = (user_doc or {}).get("best_round", 1 if score > 0 else 0)

    if rank == 1:
        rank_str = "🥇 #1 (Global Champion)"
    elif rank == 2:
        rank_str = "🥈 #2 (Grandmaster)"
    elif rank == 3:
        rank_str = "🥉 #3 (Master)"
    elif rank > 0:
        rank_str = f"🏅 #{rank}"
    else:
        rank_str = "Unranked (Play a round!)"

    # Rank title tier based on score
    if score >= 500:
        tier = "👑 Word Legend"
    elif score >= 200:
        tier = "💎 Grid Grandmaster"
    elif score >= 100:
        tier = "🔥 Puzzle Master"
    elif score >= 30:
        tier = "⚡ Word Hunter"
    else:
        tier = "🌱 Arcade Rookie"

    text = (
        f"👤 <b>Player Profile — {safe_name}</b>\n\n"
        f"<blockquote>"
        f"🎖 <b>Title:</b> <code>{tier}</code>\n"
        f"🌍 <b>Global Rank:</b> <b>{rank_str}</b>\n"
        f"⭐ <b>Total Score:</b> <code>{score:,} pts</code>\n"
        f"🔤 <b>Words Found:</b> <code>{words_found:,}</code>\n"
        f"🏔 <b>Highest Round:</b> <code>Round {best_round}</code>"
        f"</blockquote>\n"
        f"💡 <i>Keep finding words in group arcade rounds to climb the global ranks!</i>"
    )

    rows = [
        [
            InlineKeyboardButton("🔄 Refresh", callback_data="profile:refresh"),
            InlineKeyboardButton("🏆 Leaderboard", callback_data="nav:lb"),
        ]
    ]
    if show_back:
        rows.append([InlineKeyboardButton("⬅️ Back to Home", callback_data="nav:home")])

    return text, InlineKeyboardMarkup(rows)


def build_leaderboard_view(
    mode: str,
    entries: list[dict],
    show_back: bool = True,
) -> tuple[str, InlineKeyboardMarkup]:
    """
    Single Source of Truth view builder for `/leaderboard`, `/top`, and `lb:*` / `nav:lb` callbacks.
    """
    medals = {0: "🥇", 1: "🥈", 2: "🥉"}

    if mode == "groups":
        header = "🏆 <b>Global Groups Leaderboard</b>\n<i>Top 10 Most Active Word Grid Arenas</i>\n\n"
        if not entries:
            body = "<blockquote>No groups have scored points yet! Use <code>/game</code> in your group to claim #1.</blockquote>"
        else:
            lines = []
            for idx, g in enumerate(entries[:10]):
                badge = medals.get(idx, f"<b>{idx + 1}.</b>")
                title = normalize_fancy_telegram_name(g.get("title", "Unknown Group"), max_len=26)
                score = g.get("score", 0)
                best_r = g.get("best_round", 1)
                lines.append(
                    f"{badge} <b>{title}</b> — <code>{score:,} pts</code> <i>(Best: R{best_r})</i>"
                )
            body = "<blockquote>" + "\n".join(lines) + "</blockquote>"

        tabs = [
            InlineKeyboardButton("👤 Top Players", callback_data="lb:users"),
            InlineKeyboardButton("👥 Top Groups ✅", callback_data="lb:groups"),
        ]
        refresh_cb = "lb:refresh:groups"
    else:
        header = "🏆 <b>Global Players Leaderboard</b>\n<i>Top 10 Word Grid Champions</i>\n\n"
        if not entries:
            body = "<blockquote>No players have scored points yet! Start a round with <code>/game</code>.</blockquote>"
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
            InlineKeyboardButton("👤 Top Players ✅", callback_data="lb:users"),
            InlineKeyboardButton("👥 Top Groups", callback_data="lb:groups"),
        ]
        refresh_cb = "lb:refresh:users"

    rows = [
        tabs,
        [
            InlineKeyboardButton("🔄 Refresh Ranks", callback_data=refresh_cb),
            InlineKeyboardButton("👤 My Profile", callback_data="nav:profile"),
        ],
    ]
    if show_back:
        rows.append([InlineKeyboardButton("⬅️ Back to Home", callback_data="nav:home")])

    return header + body, InlineKeyboardMarkup(rows)


def build_admin_view(
    section: str = "home",
    total_users: int = 0,
    total_groups: int = 0,
    active_games_count: int = 0,
) -> tuple[str, InlineKeyboardMarkup]:
    """
    Single Source of Truth view builder for `/panel`, `/admin`, and `admin:*` callbacks.
    """
    if section == "stats":
        text = (
            "📊 <b>Word Grid Arcade — Live Bot Statistics</b>\n\n"
            "<blockquote>"
            f"👤 <b>Registered Users:</b> <code>{total_users:,}</code>\n"
            f"👥 <b>Connected Groups:</b> <code>{total_groups:,}</code>\n"
            f"🎮 <b>Active Games Running:</b> <code>{active_games_count}</code>"
            "</blockquote>\n"
            "⚡ <i>Database pool & TTL cache healthy.</i>"
        )
        markup = InlineKeyboardMarkup(
            [
                [InlineKeyboardButton("🔄 Refresh Stats", callback_data="admin:stats")],
                [InlineKeyboardButton("⬅️ Back to Panel", callback_data="admin:home")],
            ]
        )
        return text, markup

    if section == "broadcast":
        text = (
            "📢 <b>Admin Broadcast Guide</b>\n\n"
            "<blockquote>"
            "1. Send or forward any message (text, photo, video, or sticker) in this chat.\n"
            "2. Reply to that message with <code>/broadcast</code>.\n"
            "3. The bot will safely broadcast it to all registered users and groups with automatic FloodWait protection."
            "</blockquote>"
        )
        markup = InlineKeyboardMarkup(
            [[InlineKeyboardButton("⬅️ Back to Panel", callback_data="admin:home")]]
        )
        return text, markup

    text = (
        "🛠 <b>Word Grid Arcade — Admin Control Panel</b>\n\n"
        "<blockquote>"
        "Manage bot statistics, monitor active group sessions, and broadcast announcements."
        "</blockquote>"
    )
    markup = InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton("📊 Live Bot Stats", callback_data="admin:stats"),
                InlineKeyboardButton("📢 Broadcast Guide", callback_data="admin:broadcast"),
            ]
        ]
    )
    return text, markup
