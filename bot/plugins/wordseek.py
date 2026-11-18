import html
import time
import asyncio
import logging
from pyrogram import Client, filters
from pyrogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from pyrogram.enums import ChatType, ChatMemberStatus
from bot.config import (
    SUDO_USERS,
    CMD_COOLDOWN,
    GAME_START_COOLDOWN,
    HINT_COOLDOWN,
    CALLBACK_COOLDOWN,
    GUESS_COOLDOWN,
    WORDSEEK_MAX_GUESSES,
)
from bot.utils.cooldown import (
    check_cooldown,
    get_chat_lock,
    get_user_lock,
    safe_tg_call,
)
from bot.utils.wordseek_engine import (
    select_random_seek_word,
    is_valid_seek_guess,
    evaluate_guess,
    format_guess_emoji_row,
    format_word_details,
    generate_wordle_share_text,
    render_wordseek_image,
    DAILY_WORD_LIST,
    COMMON_WORDS_DETAILS,
)
from bot.utils.views import (
    normalize_fancy_telegram_name,
    build_wordseek_board_view,
    build_seek_score_view,
    build_seek_leaderboard_view,
)
from bot.database.db import (
    add_user,
    add_group,
    add_seek_score,
    get_seek_leaderboard,
    get_seek_user_score,
    find_user_by_username_or_id,
    get_current_game_date_string,
    get_or_create_daily_word,
    get_daily_guesses,
    add_daily_guess,
    update_daily_streak,
    is_seek_authorized,
    authorize_seek_user,
    remove_seek_user,
    list_seek_users,
    set_game_topic,
    unset_game_topic,
    get_game_topics,
    set_topic_allowed_lengths,
    is_user_banned,
)
from bot.plugins.game import ALL_KNOWN_COMMANDS

logger = logging.getLogger("WordGridBot.WordSeek")

# Active WordSeek sessions keyed by `(chat_id, topic_id)`
active_seek_games: dict[tuple[int, str], dict] = {}

# Active Daily WordSeek sessions in private chat keyed by `user_id`
active_daily_sessions: dict[int, dict] = {}


def _get_topic_id(message: Message) -> str:
    thread_id = getattr(message, "message_thread_id", None)
    return str(thread_id) if thread_id else "general"


async def _check_allowed_topic(message: Message) -> tuple[bool, list[int]]:
    """Checks if the chat has forum topic restrictions and returns `(is_allowed, allowed_lengths)`."""
    if message.chat.type == ChatType.PRIVATE:
        return True, [5, 4, 6]
    topics = await get_game_topics(message.chat.id)
    if not topics:
        return True, [5, 4, 6]
    current_topic = _get_topic_id(message)
    for t in topics:
        if str(t.get("topic_id")) == current_topic:
            return True, t.get("allowed_lengths", [5, 4, 6])
    return False, [5, 4, 6]


async def _is_chat_admin(client: Client, chat_id: int, user_id: int) -> bool:
    if user_id in SUDO_USERS:
        return True
    try:
        member = await client.get_chat_member(chat_id, user_id)
        return member.status in (ChatMemberStatus.OWNER, ChatMemberStatus.ADMINISTRATOR)
    except Exception:
        return False


# ============================================================================
# START WORDSEEK GAME (/wordseek, /new, /new4, /new5, /new6)
# ============================================================================
async def _start_wordseek_game(
    client: Client,
    message: Message,
    forced_length: int | None = None,
    starter_user=None,
):
    user = starter_user or message.from_user
    if not user or await is_user_banned(user.id):
        return

    chat_id = message.chat.id
    topic_id = _get_topic_id(message)
    session_key = (chat_id, topic_id)

    topic_ok, allowed_lengths = await _check_allowed_topic(message)
    if not topic_ok:
        await safe_tg_call(
            message.reply_text,
            "⚠️ <b>Games are restricted to designated game topics in this group.</b>",
            quote=True,
        )
        return

    # Determine requested word length
    word_length = forced_length
    if word_length is None:
        args = message.command[1:] if message.command and len(message.command) > 1 else []
        if args and args[0].strip() in ("4", "5", "6"):
            word_length = int(args[0].strip())
        else:
            word_length = allowed_lengths[0] if allowed_lengths else 5

    if word_length not in (4, 5, 6) or word_length not in allowed_lengths:
        allowed_str = ", ".join(str(x) for x in allowed_lengths)
        await safe_tg_call(
            message.reply_text,
            f"⚠️ <b>Only these word lengths are allowed here:</b> <code>{allowed_str}</code>",
            quote=True,
        )
        return

    allowed_cd, wait_s = check_cooldown(f"seekstart:{chat_id}:{topic_id}", GAME_START_COOLDOWN)
    if not allowed_cd:
        await safe_tg_call(
            message.reply_text,
            f"⏳ <b>Wait {wait_s}s before starting a new WordSeek game!</b>",
        )
        return

    async with get_chat_lock(chat_id):
        if session_key in active_seek_games:
            await safe_tg_call(
                message.reply_text,
                "⚠️ <b>A WordSeek game is already in progress in this chat!</b>\nUse <code>/end</code> to end the current game.",
                quote=True,
            )
            return

        if message.chat.type == ChatType.PRIVATE:
            await add_user(user.id, user.username, user.first_name)
        else:
            await add_group(chat_id, message.chat.title)

        secret_word = select_random_seek_word(chat_id, word_length)
        active_seek_games[session_key] = {
            "word": secret_word,
            "word_length": word_length,
            "chat_id": chat_id,
            "topic_id": topic_id,
            "started_by": user.id,
            "guesses": [],
            "guessed_set": set(),
            "voters": set(),
            "hint_revealed": set(),
            "created_at": time.monotonic(),
        }

    markup = InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton("💡 Hint", callback_data="ws:hint"),
                InlineKeyboardButton("🛑 End", callback_data="ws:end"),
            ]
        ]
    )
    await safe_tg_call(
        message.reply_text,
        (
            f"🟩 <b>WordSeek Started! ({word_length}-Letter Mode)</b>\n\n"
            f"<blockquote>Guess the hidden <b>{word_length}-letter word</b> by typing it in chat!\n"
            f"• Max Attempts: <code>{WORDSEEK_MAX_GUESSES}</code>\n"
            f"• Starter: <b>{normalize_fancy_telegram_name(user.first_name)}</b></blockquote>"
        ),
        reply_markup=markup,
    )


@Client.on_message(filters.command(["wordseek", "new", "new4", "new5", "new6"]))
async def wordseek_start_commands(client: Client, message: Message):
    cmd = message.command[0].lower()
    forced = None
    if cmd == "new4":
        forced = 4
    elif cmd == "new5":
        forced = 5
    elif cmd == "new6":
        forced = 6
    await _start_wordseek_game(client, message, forced_length=forced)


# ============================================================================
# END WORDSEEK GAME (/end, /endseek) & VOTING
# ============================================================================
async def _finish_and_reveal_seek(message_or_chat, client: Client, game: dict, reason_html: str):
    session_key = (game["chat_id"], game["topic_id"])
    active_seek_games.pop(session_key, None)

    w = game["word"]
    wlen = game["word_length"]
    details_block = format_word_details(w)

    text = (
        f"<blockquote>🎮 <b>WordSeek Ended</b></blockquote>\n"
        f"{details_block}\n"
        f"<blockquote>{reason_html + chr(10) if reason_html else ''}"
        f"Start a new game with <code>/new{wlen}</code></blockquote>"
    )
    markup = InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton(f"▶️ New {wlen}L", callback_data=f"ws:new:{wlen}"),
                InlineKeyboardButton("🏆 Ranks", callback_data=f"wslb:global:all:{wlen}"),
            ]
        ]
    )
    if isinstance(message_or_chat, Message):
        await safe_tg_call(message_or_chat.reply_text, text, reply_markup=markup)
    else:
        await safe_tg_call(client.send_message, int(message_or_chat), text, reply_markup=markup)


@Client.on_message(filters.command(["end", "endseek"]))
async def end_wordseek_command(client: Client, message: Message):
    user = message.from_user
    if not user or await is_user_banned(user.id):
        return

    chat_id = message.chat.id
    topic_id = _get_topic_id(message)
    session_key = (chat_id, topic_id)

    async with get_chat_lock(chat_id):
        game = active_seek_games.get(session_key)
        if not game:
            await safe_tg_call(
                message.reply_text,
                "ℹ️ <b>There is no WordSeek game in progress.</b>\nStart one with <code>/new</code>!",
                quote=True,
            )
            return

        is_private = message.chat.type == ChatType.PRIVATE
        is_starter = int(game.get("started_by", 0)) == user.id
        is_sys_admin = user.id in SUDO_USERS
        is_grp_admin = False if is_private else await _is_chat_admin(client, chat_id, user.id)
        is_auth = False if is_private else await is_seek_authorized(chat_id, user.id)

        user_link = f'<a href="tg://user?id={user.id}">{normalize_fancy_telegram_name(user.first_name)}</a>'

        if is_private or is_starter or is_sys_admin or is_grp_admin or is_auth:
            if is_private:
                reason = ""
            elif is_starter:
                reason = f"<b>Ended by game starter:</b> {user_link}"
            elif is_sys_admin:
                reason = f"<b>Ended by system admin:</b> {user_link}"
            elif is_grp_admin:
                reason = f"<b>Ended by group admin:</b> {user_link}"
            else:
                reason = f"<b>Ended by authorized user:</b> {user_link}"

            await _finish_and_reveal_seek(message, client, game, reason)
            return

        # Initiate or update 3-player vote to end
        voters: set[int] = game.setdefault("voters", set())
        voters.add(user.id)
        count = len(voters)

        if count >= 3:
            reason = f"<b>Ended by player vote ({count}/3)</b>"
            await _finish_and_reveal_seek(message, client, game, reason)
            return

    markup = InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton(
                    f"✅ Vote ({count}/3)",
                    callback_data=f"ws:vote_end:{topic_id}",
                )
            ]
        ]
    )
    await safe_tg_call(
        message.reply_text,
        (
            f"🗳 <b>Vote to End WordSeek</b>\n\n"
            f"<blockquote>{user_link} wants to end the current game.\n"
            f"• <b>Votes Needed:</b> <code>3</code>\n"
            f"• <b>Current Votes:</b> <code>{count}/3</code></blockquote>\n"
            f"<i>Tap below to vote for ending the game.</i>"
        ),
        reply_markup=markup,
    )


# ============================================================================
# DAILY WORDSEEK (/daily, /pausedaily) — PRIVATE CHAT MODE
# ============================================================================
async def _start_daily_wordseek(client: Client, user, reply_target: Message):
    if await is_user_banned(user.id):
        return

    await add_user(user.id, user.username, user.first_name)
    date_str = get_current_game_date_string()
    daily_word = await get_or_create_daily_word(date_str, DAILY_WORD_LIST, COMMON_WORDS_DETAILS)
    existing_guesses_docs = await get_daily_guesses(user.id, date_str)
    guesses = [d["guess"] for d in existing_guesses_docs]
    target_w = daily_word["word"].lower()

    if guesses:
        if guesses[-1].lower() == target_w:
            await safe_tg_call(
                reply_target.reply_text,
                (
                    f"✅ <b>You've already completed today's Daily WordSeek!</b>\n"
                    f"<blockquote>Solved in <b>{len(guesses)}/6</b> {'try' if len(guesses) == 1 else 'tries'}.\n"
                    f"Come back after <b>6:00 AM</b> tomorrow for a new challenge!</blockquote>"
                ),
            )
            return

        if len(guesses) >= 6:
            await safe_tg_call(
                reply_target.reply_text,
                (
                    f"❌ <b>You've used all 6 attempts for today's Daily WordSeek!</b>\n"
                    f"{format_word_details(target_w, daily_word)}\n"
                    f"<i>Come back after 6:00 AM tomorrow for a new challenge!</i>"
                ),
            )
            return

    active_daily_sessions[user.id] = {
        "date": date_str,
        "word": target_w,
        "day_number": daily_word.get("day_number", 1),
        "daily_doc": daily_word,
    }

    attempts_left = 6 - len(guesses)
    if guesses:
        img_io = await asyncio.to_thread(render_wordseek_image, guesses, target_w, 6)
        await safe_tg_call(
            reply_target.reply_photo,
            photo=img_io,
            caption=(
                f"🎯 <b>Daily WordSeek Resumed!</b>\n"
                f"You have <b>{attempts_left}</b> {'attempt' if attempts_left == 1 else 'attempts'} left. Type a 5-letter word!"
            ),
        )
    else:
        await safe_tg_call(
            reply_target.reply_text,
            (
                "🎯 <b>WordSeek of the Day Started!</b>\n\n"
                "<blockquote>• Guess today's <b>5-letter word</b> in <b>6 attempts</b>.\n"
                "• Each guess generates a visual Wordle tile board.\n"
                "• Use <code>/pausedaily</code> anytime to switch to regular <code>/new</code> mode.</blockquote>\n"
                "💬 <i>Type your first 5-letter guess now!</i>"
            ),
        )


@Client.on_message(filters.command(["daily", "pausedaily"]))
async def daily_wordseek_commands(client: Client, message: Message):
    user = message.from_user
    if not user or await is_user_banned(user.id):
        return

    cmd = message.command[0].lower()
    if message.chat.type != ChatType.PRIVATE:
        uname = getattr(client.me, "username", None) or "WordGridGameBot"
        markup = InlineKeyboardMarkup(
            [[InlineKeyboardButton("🎯 Play Daily in DM", url=f"https://t.me/{uname}?start=daily")]]
        )
        await safe_tg_call(
            message.reply_text,
            "🎯 <b>Daily WordSeek is only available in Private Chat (DM)!</b>",
            reply_markup=markup,
            quote=True,
        )
        return

    if cmd == "pausedaily":
        if user.id not in active_daily_sessions:
            await safe_tg_call(
                message.reply_text,
                "ℹ️ <b>You don't have an active Daily WordSeek session to pause.</b>",
            )
            return
        active_daily_sessions.pop(user.id, None)
        await safe_tg_call(
            message.reply_text,
            "✅ <b>Daily WordSeek paused!</b>\nYou can now play regular WordSeek with <code>/new</code>, or resume anytime with <code>/daily</code>.",
        )
        return

    session_key = (message.chat.id, "general")
    if session_key in active_seek_games:
        await safe_tg_call(
            message.reply_text,
            "⚠️ <b>You have a regular WordSeek game running!</b>\nUse <code>/end</code> first before starting <code>/daily</code>.",
        )
        return

    await _start_daily_wordseek(client, user, message)


# ============================================================================
# SCORE & MYSCORE COMMANDS (/score, /myscore)
# ============================================================================
def _parse_score_args(args: list[str], is_private: bool) -> tuple[str | None, str, str, int]:
    target = None
    search_key = "global" if is_private else "group"
    time_key = "all"
    word_length = 5

    for raw in args:
        tok = raw.strip()
        low = tok.lower()
        if low in ("global", "group", "chat"):
            search_key = "group" if low in ("group", "chat") else "global"
        elif low in ("today", "week", "month", "year", "all"):
            time_key = low
        elif low in ("4", "5", "6", "4l", "5l", "6l"):
            word_length = int(low[0])
        elif tok.startswith("@") or tok.isdigit():
            target = tok
    return target, search_key, time_key, word_length


@Client.on_message(filters.command(["score", "myscore"]))
async def score_command(client: Client, message: Message):
    user = message.from_user
    if not user or await is_user_banned(user.id):
        return

    allowed, _ = check_cooldown(f"cmd:score:{user.id}", CMD_COOLDOWN)
    if not allowed:
        return

    is_private = message.chat.type == ChatType.PRIVATE
    args = message.command[1:] if message.command and len(message.command) > 1 else []
    target_str, s_key, t_key, w_len = _parse_score_args(args, is_private)

    target_id = user.id
    target_name = user.first_name

    if message.reply_to_message and message.reply_to_message.from_user and not target_str:
        r_user = message.reply_to_message.from_user
        if not r_user.is_bot:
            target_id = r_user.id
            target_name = r_user.first_name
    elif target_str:
        found = await find_user_by_username_or_id(target_str)
        if not found:
            await safe_tg_call(message.reply_text, "❌ <b>User not found in database.</b>", quote=True)
            return
        target_id = int(found["user_id"])
        target_name = found.get("first_name", "Player")

    score_data = await get_seek_user_score(
        user_id=target_id,
        chat_id=message.chat.id,
        search_key=s_key,
        time_key=t_key,
        word_length=w_len,
    )
    text, markup = build_seek_score_view(
        score_data=score_data,
        target_id=target_id,
        target_name=target_name,
        search_key=s_key,
        time_key=t_key,
        word_length=w_len,
    )
    await safe_tg_call(message.reply_text, text, reply_markup=markup, quote=True)


# ============================================================================
# GROUP SETTINGS COMMANDS (/seekauth, /setgametopic, /unsetgametopic, /allowonlylen, /id)
# ============================================================================
@Client.on_message(filters.command(["seekauth"]))
async def seekauth_command(client: Client, message: Message):
    user = message.from_user
    if not user or message.chat.type == ChatType.PRIVATE:
        return

    if not await _is_chat_admin(client, message.chat.id, user.id):
        await safe_tg_call(
            message.reply_text,
            "❌ <b>Only group administrators can manage authorized WordSeek users.</b>",
            quote=True,
        )
        return

    args = message.command[1:] if message.command and len(message.command) > 1 else []
    action = args[0].lower() if args else ""

    if action == "list":
        auth_list = await list_seek_users(message.chat.id)
        if not auth_list:
            await safe_tg_call(message.reply_text, "📋 <b>No authorized users in this chat.</b>", quote=True)
            return
        lines = []
        for u in auth_list:
            uid = u.get("user_id")
            nm = normalize_fancy_telegram_name(u.get("name", "User"))
            lines.append(f"• <a href=\"tg://user?id={uid}\">{nm}</a> (<code>{uid}</code>)")
        await safe_tg_call(
            message.reply_text,
            "🔐 <b>Authorized WordSeek Users:</b>\n<blockquote>" + "\n".join(lines) + "</blockquote>",
            quote=True,
        )
        return

    if action == "remove":
        target_user = None
        if message.reply_to_message and message.reply_to_message.from_user:
            target_user = message.reply_to_message.from_user
            t_id = target_user.id
            t_name = target_user.first_name
        elif len(args) > 1:
            doc = await find_user_by_username_or_id(args[1])
            if doc:
                t_id = int(doc["user_id"])
                t_name = doc.get("first_name", "User")
            else:
                await safe_tg_call(message.reply_text, "❌ <b>User not found.</b>", quote=True)
                return
        else:
            await safe_tg_call(
                message.reply_text,
                "ℹ️ <b>Usage:</b> Reply to a user or send <code>/seekauth remove @username</code>",
                quote=True,
            )
            return

        removed = await remove_seek_user(message.chat.id, t_id)
        if removed:
            await safe_tg_call(
                message.reply_text,
                f"✅ <b>Removed {normalize_fancy_telegram_name(t_name)} from authorized users.</b>",
                quote=True,
            )
        else:
            await safe_tg_call(message.reply_text, "ℹ️ <b>User was not in the authorized list.</b>", quote=True)
        return

    # Authorize a user (via reply or /seekauth @username)
    t_id = None
    t_name = "User"
    t_uname = None
    if message.reply_to_message and message.reply_to_message.from_user:
        ru = message.reply_to_message.from_user
        t_id, t_name, t_uname = ru.id, ru.first_name, ru.username
    elif args:
        ident = args[1] if action == "add" and len(args) > 1 else args[0]
        doc = await find_user_by_username_or_id(ident)
        if doc:
            t_id = int(doc["user_id"])
            t_name = doc.get("first_name", "User")
            t_uname = doc.get("display_username")

    if not t_id:
        await safe_tg_call(
            message.reply_text,
            "ℹ️ <b>Usage:</b>\n• Reply to a user with <code>/seekauth</code>\n• <code>/seekauth @username</code>\n• <code>/seekauth remove @username</code>\n• <code>/seekauth list</code>",
            quote=True,
        )
        return

    await authorize_seek_user(message.chat.id, t_id, t_name, t_uname, user.id)
    await safe_tg_call(
        message.reply_text,
        f"✅ <b>Authorized <a href=\"tg://user?id={t_id}\">{normalize_fancy_telegram_name(t_name)}</a> to manage WordSeek games!</b>",
        quote=True,
    )


@Client.on_message(filters.command(["setgametopic", "unsetgametopic", "allowonlylen"]))
async def forum_topic_commands(client: Client, message: Message):
    user = message.from_user
    if not user or message.chat.type == ChatType.PRIVATE:
        return

    if not await _is_chat_admin(client, message.chat.id, user.id):
        await safe_tg_call(message.reply_text, "❌ <b>Admin permission required.</b>", quote=True)
        return

    cmd = message.command[0].lower()
    topic_id = _get_topic_id(message)

    if cmd == "setgametopic":
        created = await set_game_topic(message.chat.id, topic_id)
        if created:
            await safe_tg_call(
                message.reply_text,
                f"✅ <b>Topic <code>{topic_id}</code> is now set as an active game topic!</b>",
                quote=True,
            )
        else:
            await safe_tg_call(
                message.reply_text,
                "ℹ️ <b>This topic is already registered.</b> Use <code>/unsetgametopic</code> to remove it.",
                quote=True,
            )
    elif cmd == "unsetgametopic":
        await unset_game_topic(message.chat.id, topic_id)
        await safe_tg_call(
            message.reply_text,
            f"✅ <b>Removed game restriction for topic <code>{topic_id}</code>.</b>",
            quote=True,
        )
    elif cmd == "allowonlylen":
        args = message.command[1:] if message.command and len(message.command) > 1 else []
        lengths = []
        for a in args:
            if a.strip() in ("4", "5", "6") and int(a.strip()) not in lengths:
                lengths.append(int(a.strip()))
        if not lengths:
            await safe_tg_call(
                message.reply_text,
                "ℹ️ <b>Usage:</b> <code>/allowonlylen 5 4 6</code> (Allowed values: 4, 5, 6)",
                quote=True,
            )
            return
        await set_game_topic(message.chat.id, topic_id)
        await set_topic_allowed_lengths(message.chat.id, topic_id, lengths)
        await safe_tg_call(
            message.reply_text,
            f"✅ <b>Allowed WordSeek lengths updated!</b>\n• Default: <code>{lengths[0]}L</code>\n• Allowed: <code>{', '.join(str(x) for x in lengths)}</code>",
            quote=True,
        )


@Client.on_message(filters.command(["id"]))
async def id_command(client: Client, message: Message):
    user = message.from_user
    if not user:
        return
    if message.chat.type != ChatType.PRIVATE and not await _is_chat_admin(client, message.chat.id, user.id):
        return

    lines = [
        f"💬 <b>Chat ID:</b> <code>{message.chat.id}</code>",
        f"👤 <b>Your ID:</b> <code>{user.id}</code>",
        f"📨 <b>Message ID:</b> <code>{message.id}</code>",
    ]
    t_id = getattr(message, "message_thread_id", None)
    if t_id:
        lines.append(f"🧵 <b>Topic ID:</b> <code>{t_id}</code>")
    if message.reply_to_message:
        rm = message.reply_to_message
        lines.append(f"↩️ <b>Replied Msg ID:</b> <code>{rm.id}</code>")
        if rm.from_user:
            lines.append(f"👥 <b>Replied User ID:</b> <code>{rm.from_user.id}</code>")
    await safe_tg_call(message.reply_text, "<blockquote>" + "\n".join(lines) + "</blockquote>", quote=True)


# ============================================================================
# WORDSEEK CALLBACK HANDLERS (wh:, ws:, wslb:, wsscore:)
# ============================================================================
@Client.on_callback_query(filters.regex(r"^(wh:|ws:|wslb:|wsscore:)"))
async def wordseek_callbacks(client: Client, query: CallbackQuery):
    user = query.from_user
    if not user or await is_user_banned(user.id):
        await query.answer()
        return

    data = query.data

    # 1. Letter color hint toast (`wh:<state>:<letter>`)
    if data.startswith("wh:"):
        parts = data.split(":")
        state = parts[1] if len(parts) > 1 else ""
        letter = parts[2] if len(parts) > 2 else "?"
        hints = {
            "correct": f'🟩 "{letter}" is in the word and in the right spot.',
            "present": f'🟨 "{letter}" is in the word, but in a different spot.',
            "absent": f'🟥 "{letter}" is not in the word.',
        }
        await query.answer(hints.get(state, "Letter hint"), show_alert=False)
        return

    allowed_cb, wait_s = check_cooldown(f"cb:ws:{user.id}", CALLBACK_COOLDOWN)
    if not allowed_cb:
        await query.answer(f"⏳ Wait {wait_s}s!", show_alert=False)
        return

    # 2. WordSeek game control callbacks (`ws:...`)
    if data.startswith("ws:"):
        if not query.message:
            await query.answer()
            return
        chat_id = query.message.chat.id
        parts = data.split(":")
        action = parts[1] if len(parts) > 1 else ""

        if action == "daily":
            if query.message.chat.type != ChatType.PRIVATE:
                await query.answer("Use /daily in private chat!", show_alert=True)
                return
            await query.answer("🎯 Starting Daily WordSeek!")
            await _start_daily_wordseek(client, user, query.message)
            return

        if action == "new":
            wlen = int(parts[2]) if len(parts) > 2 and parts[2].isdigit() else 5
            await query.answer(f"🟩 Starting {wlen}-letter WordSeek!")
            await _start_wordseek_game(client, query.message, forced_length=wlen, starter_user=user)
            return

        topic_id = parts[2] if len(parts) > 2 else _get_topic_id(query.message)
        session_key = (chat_id, topic_id)

        if action == "hint":
            async with get_chat_lock(chat_id):
                game = active_seek_games.get(session_key)
                if not game:
                    await query.answer("⚠️ No active WordSeek game!", show_alert=True)
                    return
                ok_h, h_wait = check_cooldown(f"wshint:{chat_id}:{topic_id}", HINT_COOLDOWN)
                if not ok_h:
                    await query.answer(f"⏳ Hint cooldown: wait {h_wait}s!", show_alert=True)
                    return

                sol = game["word"].upper()
                rev: set[int] = game.setdefault("hint_revealed", set())
                if len(rev) >= 2:
                    await query.answer("⚠️ Max 2 letter hints per WordSeek game!", show_alert=True)
                    return
                avail_idx = [i for i in range(len(sol)) if i not in rev]
                if avail_idx:
                    import random as _rnd
                    rev.add(_rnd.choice(avail_idx))
                pattern = " ".join(sol[i] if i in rev else "_" for i in range(len(sol)))

            await query.answer(f"💡 Pattern: {pattern}", show_alert=False)
            await safe_tg_call(
                query.message.reply_text,
                f"💡 <b>WordSeek Hint:</b> <code>{pattern}</code> <b>({len(sol)}L)</b>",
            )
            return

        if action in ("end", "vote_end"):
            async with get_chat_lock(chat_id):
                game = active_seek_games.get(session_key)
                if not game:
                    await query.answer("ℹ️ Game already ended.", show_alert=False)
                    return

                is_private = query.message.chat.type == ChatType.PRIVATE
                is_starter = int(game.get("started_by", 0)) == user.id
                is_sys_admin = user.id in SUDO_USERS
                is_grp_admin = False if is_private else await _is_chat_admin(client, chat_id, user.id)
                is_auth = False if is_private else await is_seek_authorized(chat_id, user.id)
                user_link = f'<a href="tg://user?id={user.id}">{normalize_fancy_telegram_name(user.first_name)}</a>'

                if action == "end" and (is_private or is_starter or is_sys_admin or is_grp_admin or is_auth):
                    reason = f"<b>Ended by:</b> {user_link}" if not is_private else ""
                    await _finish_and_reveal_seek(chat_id, client, game, reason)
                    await query.answer("🛑 Game ended!")
                    return

                voters: set[int] = game.setdefault("voters", set())
                if user.id in voters:
                    await query.answer("⏳ You already voted to end!", show_alert=False)
                    return
                voters.add(user.id)
                count = len(voters)

                if count >= 3:
                    reason = f"<b>Ended by player vote ({count}/3)</b>"
                    await _finish_and_reveal_seek(chat_id, client, game, reason)
                    await query.answer("✅ Vote passed! Game ended.")
                    return

            markup = InlineKeyboardMarkup(
                [
                    [
                        InlineKeyboardButton(
                            f"✅ Vote ({count}/3)",
                            callback_data=f"ws:vote_end:{topic_id}",
                        )
                    ]
                ]
            )
            if action == "vote_end":
                await safe_tg_call(
                    query.message.edit_text,
                    (
                        f"🗳 <b>Vote to End WordSeek</b>\n\n"
                        f"<blockquote>• <b>Votes Needed:</b> <code>3</code>\n"
                        f"• <b>Current Votes:</b> <code>{count}/3</code></blockquote>\n"
                        f"<i>Tap below to vote for ending the game.</i>"
                    ),
                    reply_markup=markup,
                )
            else:
                await safe_tg_call(
                    query.message.reply_text,
                    (
                        f"🗳 <b>Vote to End WordSeek</b>\n\n"
                        f"<blockquote>{user_link} wants to end the game.\n"
                        f"• <b>Current Votes:</b> <code>{count}/3</code></blockquote>"
                    ),
                    reply_markup=markup,
                )
            await query.answer(f"🗳 Vote recorded ({count}/3)!")
            return

    # 3. WordSeek Leaderboard filter callbacks (`wslb:<search>:<time>:<len>[:r]`)
    if data.startswith("wslb:"):
        async with get_user_lock(user.id):
            parts = data.split(":")
            s_key = parts[1] if len(parts) > 1 else "global"
            t_key = parts[2] if len(parts) > 2 else "all"
            w_len = int(parts[3]) if len(parts) > 3 and parts[3].isdigit() else 5
            force_ref = len(parts) > 4 and parts[4] == "r"

            chat_id = query.message.chat.id if query.message else user.id
            entries = await get_seek_leaderboard(
                chat_id=chat_id,
                search_key=s_key,
                time_key=t_key,
                word_length=w_len,
                force_refresh=force_ref,
            )
            show_back = bool(
                query.message
                and (query.message.chat.type == ChatType.PRIVATE or query.message.photo)
            )
            text, markup = build_seek_leaderboard_view(
                entries=entries,
                search_key=s_key,
                time_key=t_key,
                word_length=w_len,
                show_back=show_back,
            )
            if query.message and query.message.photo:
                await safe_tg_call(query.message.edit_caption, caption=text, reply_markup=markup)
            elif query.message:
                await safe_tg_call(query.message.edit_text, text=text, reply_markup=markup)
            await query.answer("🔄 Refreshed!" if force_ref else "")
        return

    # 4. WordSeek User Score filter callbacks (`wsscore:<target_id>:<search>:<time>:<len>[:r]`)
    if data.startswith("wsscore:"):
        async with get_user_lock(user.id):
            parts = data.split(":")
            target_id = int(parts[1]) if len(parts) > 1 and parts[1].lstrip("-").isdigit() else user.id
            s_key = parts[2] if len(parts) > 2 else "global"
            t_key = parts[3] if len(parts) > 3 else "all"
            w_len = int(parts[4]) if len(parts) > 4 and parts[4].isdigit() else 5

            chat_id = query.message.chat.id if query.message else user.id
            score_data = await get_seek_user_score(
                user_id=target_id,
                chat_id=chat_id,
                search_key=s_key,
                time_key=t_key,
                word_length=w_len,
            )
            text, markup = build_seek_score_view(
                score_data=score_data,
                target_id=target_id,
                target_name=user.first_name if target_id == user.id else "Player",
                search_key=s_key,
                time_key=t_key,
                word_length=w_len,
            )
            if query.message:
                await safe_tg_call(query.message.edit_text, text=text, reply_markup=markup)
            await query.answer()


# ============================================================================
# WORDSEEK TEXT GUESS HANDLER (Group & Private / Daily)
# ============================================================================
@Client.on_message(
    filters.text
    & ~filters.bot
    & ~filters.command(ALL_KNOWN_COMMANDS),
    group=2,
)
async def handle_wordseek_guess(client: Client, message: Message):
    if not message.text or not message.from_user:
        return

    raw_text = message.text.strip().lower()
    if not raw_text.isalpha() or not (4 <= len(raw_text) <= 6):
        return

    user = message.from_user
    if await is_user_banned(user.id):
        return

    chat_id = message.chat.id

    # 1. Check active Daily WordSeek in Private Chat
    if message.chat.type == ChatType.PRIVATE and user.id in active_daily_sessions:
        if len(raw_text) != 5:
            return
        session = active_daily_sessions[user.id]
        today_str = get_current_game_date_string()
        if session.get("date") != today_str:
            active_daily_sessions.pop(user.id, None)
            await safe_tg_call(
                message.reply_text,
                "⏰ <b>Your previous Daily session expired.</b> Send <code>/daily</code> to start today's challenge!",
            )
            return

        if not is_valid_seek_guess(raw_text, 5):
            await safe_tg_call(
                message.reply_text,
                f"❌ <code>{raw_text.upper()}</code> is not a valid 5-letter English word.",
                quote=True,
            )
            return

        existing_docs = await get_daily_guesses(user.id, today_str)
        guesses = [d["guess"] for d in existing_docs]
        if raw_text in guesses:
            await safe_tg_call(
                message.reply_text,
                "⚠️ <b>You already guessed that word!</b> Try a different 5-letter word.",
                quote=True,
            )
            return

        attempt_num = len(guesses) + 1
        await add_daily_guess(user.id, today_str, raw_text, attempt_num)
        guesses.append(raw_text)

        target_w = session["word"].lower()
        day_num = session.get("day_number", 1)
        daily_doc = session.get("daily_doc", {})

        img_io = await asyncio.to_thread(render_wordseek_image, guesses, target_w, 6)

        if raw_text == target_w:
            active_daily_sessions.pop(user.id, None)
            curr_s, high_s = await update_daily_streak(user.id, True, today_str)
            share_txt = generate_wordle_share_text(day_num, guesses, target_w)
            await add_seek_score(user.id, user.first_name, user.username, chat_id, (7 - len(guesses)) * 5, 5)

            markup = InlineKeyboardMarkup(
                [[InlineKeyboardButton("📤 Share Result", switch_inline_query=share_txt)]]
            )
            await safe_tg_call(
                message.reply_photo,
                photo=img_io,
                caption=(
                    f"🎉 <b>Congratulations! You solved Daily WordSeek #{day_num} in {len(guesses)}/6!</b>\n\n"
                    f"🔥 <b>Current Streak:</b> <code>{curr_s}</code>  •  ⭐ <b>Best Streak:</b> <code>{high_s}</code>\n\n"
                    f"{format_word_details(target_w, daily_doc)}"
                ),
                reply_markup=markup,
            )
            return

        if len(guesses) >= 6:
            active_daily_sessions.pop(user.id, None)
            await update_daily_streak(user.id, False, today_str)
            share_txt = generate_wordle_share_text(day_num, guesses, target_w)
            markup = InlineKeyboardMarkup(
                [[InlineKeyboardButton("📤 Share Result", switch_inline_query=share_txt)]]
            )
            await safe_tg_call(
                message.reply_photo,
                photo=img_io,
                caption=(
                    f"💔 <b>Game Over! Daily WordSeek #{day_num}</b>\n"
                    f"Streak reset to <code>0</code>.\n\n"
                    f"{format_word_details(target_w, daily_doc)}\n\n"
                    f"<i>Come back tomorrow for a new challenge!</i>"
                ),
                reply_markup=markup,
            )
            return

        rem = 6 - len(guesses)
        await safe_tg_call(
            message.reply_photo,
            photo=img_io,
            caption=f"🎯 <b>{rem} {'attempt' if rem == 1 else 'attempts'} remaining!</b>",
        )
        return

    # 2. Check active Regular WordSeek game in Group or Private Chat
    topic_id = _get_topic_id(message)
    session_key = (chat_id, topic_id)
    if session_key not in active_seek_games:
        return

    game = active_seek_games.get(session_key)
    if not game or len(raw_text) != game["word_length"]:
        return

    allowed_g, _ = check_cooldown(f"wsguess:{chat_id}:{user.id}", GUESS_COOLDOWN)
    if not allowed_g:
        return

    wlen = game["word_length"]
    if not is_valid_seek_guess(raw_text, wlen):
        await safe_tg_call(
            message.reply_text,
            f"❌ <code>{raw_text.upper()}</code> is not a valid {wlen}-letter word.",
            quote=True,
        )
        return

    async with get_chat_lock(chat_id):
        game = active_seek_games.get(session_key)
        if not game:
            return

        if raw_text in game["guessed_set"]:
            await safe_tg_call(
                message.reply_text,
                "⚠️ <b>Someone already guessed that word!</b> Try another one.",
                quote=True,
            )
            return

        target_w = game["word"].lower()

        if raw_text == target_w:
            prev_guesses_count = len(game["guesses"])
            score = max(1, WORDSEEK_MAX_GUESSES - prev_guesses_count)
            game["guesses"].append(raw_text)
            all_guesses = list(game["guesses"])
            active_seek_games.pop(session_key, None)

            await add_seek_score(
                user_id=user.id,
                first_name=user.first_name,
                username=user.username,
                chat_id=chat_id,
                score=score,
                word_length=wlen,
            )

            winner_name = normalize_fancy_telegram_name(user.first_name)
            board_rows = "\n".join(format_guess_emoji_row(g, target_w) for g in all_guesses[-8:])
            details_block = format_word_details(target_w)
            markup = InlineKeyboardMarkup(
                [
                    [
                        InlineKeyboardButton(f"▶️ New {wlen}L", callback_data=f"ws:new:{wlen}"),
                        InlineKeyboardButton("🏆 Ranks", callback_data=f"wslb:group:all:{wlen}"),
                    ]
                ]
            )
            await safe_tg_call(
                message.reply_text,
                (
                    f"🎉 <b>Congrats {winner_name}! You guessed it!</b>\n"
                    f"<blockquote>{board_rows}</blockquote>\n"
                    f"{details_block}\n"
                    f"<blockquote>🏆 Added <b>+{score} pts</b> to the {wlen}L leaderboard!\n"
                    f"Start again with <code>/new{wlen}</code></blockquote>"
                ),
                reply_markup=markup,
                quote=True,
            )
            return

        game["guessed_set"].add(raw_text)
        game["guesses"].append(raw_text)
        all_guesses = list(game["guesses"])

        if len(all_guesses) >= WORDSEEK_MAX_GUESSES:
            active_seek_games.pop(session_key, None)
            details_block = format_word_details(target_w)
            markup = InlineKeyboardMarkup(
                [[InlineKeyboardButton(f"▶️ New {wlen}L", callback_data=f"ws:new:{wlen}")]]
            )
            await safe_tg_call(
                message.reply_text,
                (
                    f"⏰ <b>Game Over! Maximum guesses ({WORDSEEK_MAX_GUESSES}) reached.</b>\n"
                    f"{details_block}\n"
                    f"Start a new game with <code>/new{wlen}</code>!"
                ),
                reply_markup=markup,
            )
            return

    text, markup = build_wordseek_board_view(
        guesses=all_guesses,
        solution=target_w,
        max_guesses=WORDSEEK_MAX_GUESSES,
        evaluate_fn=evaluate_guess,
        format_row_fn=format_guess_emoji_row,
    )
    await safe_tg_call(message.reply_text, text, reply_markup=markup)
