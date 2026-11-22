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
from bot.utils.rich_api import (
    send_rich_message,
    send_styled_message,
    edit_styled_message,
)
from bot.utils.wordseek_engine import (
    select_random_seek_word,
    is_valid_seek_guess,
    evaluate_guess,
    build_rich_feedback,
    format_guess_emoji_row,
    format_word_details,
    generate_wordle_share_text,
    render_wordseek_image,
    DAILY_WORD_LIST,
    COMMON_WORDS_DETAILS,
)
from bot.utils.views import (
    normalize_fancy_telegram_name,
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
from bot.utils.command_filter import bot_command, get_primary_bot_username
from bot.utils.emojis import (
    E_GAME, E_NEW, E_WARN, E_STOP, E_VERIFIED, E_CROSS, E_HOURGLASS,
    E_CLOCK24, E_BOLT, E_BEST, E_CROWN, E_SETTINGS, E_CHAT, E_USER,
    E_FILE, E_PIN, E_ANIME_COOL, E_CLOVER, ID_VERIFIED, ID_SHARE,
    make_button,
)

logger = logging.getLogger("WordGridBot.WordSeek")

# Active WordSeek sessions keyed by `(chat_id, topic_id)`
active_seek_games: dict[tuple[int, str], dict] = {}

# Active Daily WordSeek sessions in private chat keyed by `user_id`
active_daily_sessions: dict[int, dict] = {}


def _get_topic_id(message: Message) -> str:
    thread_id = getattr(message, "message_thread_id", None)
    return str(thread_id) if thread_id else "general"


async def _check_allowed_topic(message: Message) -> tuple[bool, list[int]]:
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
            f"{E_WARN} This topic is not set for the game.",
            quote=True,
        )
        return

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
            f"{E_WARN} Only these lengths are allowed in this topic: <code>{allowed_str}</code>.",
            quote=True,
        )
        return

    allowed_cd, wait_s = check_cooldown(f"seekstart:{chat_id}:{topic_id}", GAME_START_COOLDOWN)
    if not allowed_cd:
        return

    async with get_chat_lock(chat_id):
        if session_key in active_seek_games:
            await safe_tg_call(
                message.reply_text,
                f"{E_WARN} A game is already in progress in this chat. Use <code>/end</code> to finish it first.",
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
            "created_at": time.monotonic(),
        }

    await safe_tg_call(
        message.reply_text,
        f"{E_GAME} <b>WordSeek Started!</b>\n<blockquote>{E_CLOVER} Guess the hidden <b>{word_length}-letter</b> word!</blockquote>",
    )


@Client.on_message(bot_command(["wordseek", "new", "new4", "new5", "new6"]))
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

    text = (
        f"{E_STOP} <b>Game Ended</b>\n<blockquote>{E_VERIFIED} Correct Word: <b>{html.escape(w.upper())}</b></blockquote>\n"
        f"<blockquote>{reason_html + chr(10) if reason_html else ''}"
        f"{E_NEW} Start a new game with <code>/new{wlen}</code></blockquote>"
    )
    if isinstance(message_or_chat, Message):
        await safe_tg_call(message_or_chat.reply_text, text)
    else:
        await safe_tg_call(client.send_message, int(message_or_chat), text)


@Client.on_message(bot_command(["end", "endseek"]))
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
                f"{E_WARN} There is no active WordSeek game in this chat.",
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
                reason = f"<b>Ended by game starter: </b>{user_link}"
            elif is_sys_admin:
                reason = f"<b>Ended by system administrator: </b>{user_link}"
            elif is_grp_admin:
                reason = f"<b>Ended by group administrator: </b>{user_link}"
            else:
                reason = f"<b>Ended by authorized user: </b>{user_link}"

            await _finish_and_reveal_seek(message, client, game, reason)
            return

        voters: set[int] = game.setdefault("voters", set())
        if len(voters) > 0:
            await safe_tg_call(
                message.reply_text,
                f"{E_HOURGLASS} A vote to end the game is already in progress. Please wait for it to finish.",
            )
            return

        voters.add(user.id)
        count = len(voters)

    markup = InlineKeyboardMarkup(
        [
            [
                make_button(
                    f"Vote to End ({count}/3)",
                    callback_data=f"ws:vote_end:{topic_id}",
                    icon_id=ID_VERIFIED,
                    fallback_prefix="✅",
                )
            ]
        ]
    )
    await safe_tg_call(
        message.reply_text,
        (
            f"{E_WARN} <b>Vote to End Game</b>\n\n"
            f"{user_link} wants to end the game.\n\n"
            f"<b>Votes needed: 3 out of remaining players</b>\n"
            f"<b>Current votes: {count}/3</b>\n\n"
            f"React with the button below to vote for ending the game."
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
                f"You've already completed today's WordSeek! You got it in {len(guesses)} {'try' if len(guesses) == 1 else 'tries'}. Come back after 6:00 AM tomorrow for a new challenge!",
            )
            return

        if len(guesses) >= 6:
            await safe_tg_call(
                reply_target.reply_text,
                f"You've already used all 6 attempts for today's WordSeek. The word was: {target_w.upper()}\n\nCome back after 6:00 AM tomorrow for a new challenge!",
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
            caption=f"Welcome back! You have {attempts_left} {'attempt' if attempts_left == 1 else 'attempts'} left for today's WordSeek. Keep guessing!",
        )
    else:
        await safe_tg_call(
            reply_target.reply_text,
            f"{E_CLOCK24} <b>WordSeek of the Day Started!</b>\n<blockquote>{E_CLOVER} Guess the <b>5-letter</b> word in <b>6 attempts</b>. Good luck!</blockquote>",
        )


@Client.on_message(bot_command(["daily", "pausedaily"]))
async def daily_wordseek_commands(client: Client, message: Message):
    user = message.from_user
    if not user or await is_user_banned(user.id):
        return

    cmd = message.command[0].lower()
    if message.chat.type != ChatType.PRIVATE:
        await safe_tg_call(
            message.reply_text,
            f"{E_WARN} Daily WordSeek can only be played in private chat (DM)!",
            quote=True,
        )
        return

    if cmd == "pausedaily":
        if user.id not in active_daily_sessions:
            await safe_tg_call(
                message.reply_text,
                "You don't have an active WordSeek of the Day game to pause.",
            )
            return
        active_daily_sessions.pop(user.id, None)
        await safe_tg_call(
            message.reply_text,
            f"{E_VERIFIED} <b>Daily WordSeek Paused</b>\n<blockquote>You can now play regular WordSeek. Use <code>/daily</code> anytime to resume today's puzzle.</blockquote>",
        )
        return

    session_key = (message.chat.id, "general")
    if session_key in active_seek_games:
        await safe_tg_call(
            message.reply_text,
            "Please end your current regular game with /end before starting /daily.",
        )
        return

    await _start_daily_wordseek(client, user, message)


# ============================================================================
# SCORE & MYSCORE COMMANDS (/score, /myscore) WITH BOT API 10.3 BUTTON STYLES
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


@Client.on_message(bot_command(["score", "myscore"]))
async def score_command(client: Client, message: Message):
    user = message.from_user
    if not user or await is_user_banned(user.id):
        return

    allowed, _ = check_cooldown(f"cmd:score:{user.id}", CMD_COOLDOWN)
    if not allowed:
        return

    if message.command[0].lower() == "myscore":
        await safe_tg_call(
            message.reply_text,
            "Please switch to /score command. It's a replacement for /myscore command",
            quote=True,
        )
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
            await safe_tg_call(message.reply_text, "User not found.", quote=True)
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
    text, pyro_markup, styled_kb_dict = build_seek_score_view(
        score_data=score_data,
        target_id=target_id,
        target_name=target_name,
        search_key=s_key,
        time_key=t_key,
        word_length=w_len,
    )

    sent = await send_styled_message(
        chat_id=message.chat.id,
        text_html=text,
        reply_markup=styled_kb_dict,
        message_thread_id=getattr(message, "message_thread_id", None),
        reply_to_message_id=message.id,
    )
    if not sent:
        await safe_tg_call(message.reply_text, text, reply_markup=pyro_markup, quote=True)


# ============================================================================
# GROUP SETTINGS COMMANDS (/seekauth, /setgametopic, /unsetgametopic, /allowonlylen, /id)
# ============================================================================
@Client.on_message(bot_command(["seekauth"]))
async def seekauth_command(client: Client, message: Message):
    user = message.from_user
    if not user or message.chat.type == ChatType.PRIVATE:
        return

    if not await _is_chat_admin(client, message.chat.id, user.id):
        await safe_tg_call(
            message.reply_text,
            f"{E_CROSS} Only group administrators can manage authorized users.",
            quote=True,
        )
        return

    args = message.command[1:] if message.command and len(message.command) > 1 else []
    action = args[0].lower() if args else ""

    if action == "list":
        auth_list = await list_seek_users(message.chat.id)
        if not auth_list:
            await safe_tg_call(message.reply_text, f"{E_FILE} No authorized users in this chat.", quote=True)
            return
        lines = []
        for u in auth_list:
            uid = u.get("user_id")
            nm = normalize_fancy_telegram_name(u.get("name", "User"))
            un = u.get("username")
            lines.append(f'• <a href="tg://user?id={uid}">{nm}</a>{f" (@{un})" if un else ""}')
        await safe_tg_call(
            message.reply_text,
            f"{E_CROWN} <b>Authorized Users for WordSeek</b>\n\n<blockquote>" + "\n".join(lines) + "</blockquote>",
            quote=True,
        )
        return

    if action == "remove":
        t_id = None
        t_name = "User"
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
                await safe_tg_call(message.reply_text, f"{E_CROSS} User not found.", quote=True)
                return
        else:
            await safe_tg_call(
                message.reply_text,
                "Usage: /seekauth remove @username (or reply to a user)",
                quote=True,
            )
            return

        removed = await remove_seek_user(message.chat.id, t_id)
        if removed:
            await safe_tg_call(
                message.reply_text,
                f"{E_VERIFIED} Removed <b>{normalize_fancy_telegram_name(t_name)}</b> from authorized users.",
                quote=True,
            )
        else:
            await safe_tg_call(message.reply_text, f"{E_CROSS} This user is not authorized.", quote=True)
        return

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
            "Usage:\n• /seekauth @username\n• /seekauth remove @username\n• /seekauth list",
            quote=True,
        )
        return

    await authorize_seek_user(message.chat.id, t_id, t_name, t_uname, user.id)
    await safe_tg_call(
        message.reply_text,
        f'{E_VERIFIED} Authorized <a href="tg://user?id={t_id}">{normalize_fancy_telegram_name(t_name)}</a> to end WordSeek games without voting.',
        quote=True,
    )


@Client.on_message(bot_command(["setgametopic", "unsetgametopic", "allowonlylen"]))
async def forum_topic_commands(client: Client, message: Message):
    user = message.from_user
    if not user or message.chat.type == ChatType.PRIVATE:
        return

    if not await _is_chat_admin(client, message.chat.id, user.id):
        await safe_tg_call(message.reply_text, "Only administrators can use this command.", quote=True)
        return

    cmd = message.command[0].lower()
    topic_id = _get_topic_id(message)
    uname = get_primary_bot_username(client, fallback="Bot")

    if cmd == "setgametopic":
        created = await set_game_topic(message.chat.id, topic_id)
        if created:
            await safe_tg_call(
                message.reply_text,
                f"@{uname} will now use this topic for the game.",
                quote=True,
            )
        else:
            await safe_tg_call(
                message.reply_text,
                "Game has already been set for this topic.\nUse /unsetgametopic to unset it first.",
                quote=True,
            )
    elif cmd == "unsetgametopic":
        await unset_game_topic(message.chat.id, topic_id)
        await safe_tg_call(
            message.reply_text,
            f"@{uname} won't use this topic for the game.",
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
                "Usage: /allowonlylen 5 4 6",
                quote=True,
            )
            return
        await set_game_topic(message.chat.id, topic_id)
        await set_topic_allowed_lengths(message.chat.id, topic_id, lengths)
        await safe_tg_call(
            message.reply_text,
            f"Allowed word lengths updated.\nDefault length: {lengths[0]}\nAllowed: {', '.join(str(x) for x in lengths)}",
            quote=True,
        )


@Client.on_message(bot_command(["id"]))
async def id_command(client: Client, message: Message):
    user = message.from_user
    if not user:
        return
    if message.chat.type != ChatType.PRIVATE and not await _is_chat_admin(client, message.chat.id, user.id):
        return

    lines = [
        f"{E_CHAT} <b>Chat ID:</b> <code>{message.chat.id}</code>",
        f"{E_USER} <b>Your ID:</b> <code>{user.id}</code>",
        f"{E_FILE} <b>Message ID:</b> <code>{message.id}</code>",
    ]
    t_id = getattr(message, "message_thread_id", None)
    if t_id:
        lines.append(f"{E_PIN} <b>Topic ID:</b> <code>{t_id}</code>")
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

    # 1. Bot API 10.3 `<tg-button>` letter hint toast (`wh:<state>:<letter>`)
    if data.startswith("wh:"):
        parts = data.split(":")
        state = parts[1] if len(parts) > 1 else ""
        letter = parts[2] if len(parts) > 2 else "?"
        hints = {
            "correct": f'🟩 "{letter}" is in the word and in the right spot.',
            "present": f'🟨 "{letter}" is in the word, but in a different spot.',
            "absent": f'🟥 "{letter}" isn\'t in the word.',
        }
        await query.answer(hints.get(state, "Unknown hint."), show_alert=False)
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

        if action == "vote_end":
            async with get_chat_lock(chat_id):
                game = active_seek_games.get(session_key)
                if not game:
                    await query.answer("Game has already ended.", show_alert=True)
                    return

                voters: set[int] = game.setdefault("voters", set())
                if user.id in voters:
                    await query.answer("You have already voted to end the game.", show_alert=True)
                    return

                voters.add(user.id)
                count = len(voters)

                if count >= 3:
                    reason = "<b>Game ended by player vote (3/3)</b>"
                    await safe_tg_call(query.message.delete)
                    await _finish_and_reveal_seek(chat_id, client, game, reason)
                    await query.answer("Vote passed! Game ended.")
                    return

            votes_needed = 3 - count
            markup = InlineKeyboardMarkup(
                [
                    [
                        make_button(
                            f"Vote to End ({count}/3)",
                            callback_data=f"ws:vote_end:{topic_id}",
                            icon_id=ID_VERIFIED,
                            fallback_prefix="✅",
                        )
                    ]
                ]
            )
            await safe_tg_call(
                query.message.edit_text,
                (
                    f"{E_WARN} <b>Vote to End Game</b>\n\n"
                    f"<b>Votes needed: 3 out of remaining players</b>\n"
                    f"<b>Current votes: {count}/3</b>\n\n"
                    f"React with the button below to vote for ending the game."
                ),
                reply_markup=markup,
            )
            await query.answer(f"Vote recorded! {votes_needed} more votes needed.")
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
            text, pyro_markup, styled_kb_dict = build_seek_leaderboard_view(
                entries=entries,
                search_key=s_key,
                time_key=t_key,
                word_length=w_len,
                show_back=show_back,
            )
            if query.message and query.message.photo:
                await safe_tg_call(query.message.edit_caption, caption=text, reply_markup=pyro_markup)
            elif query.message:
                edited = await edit_styled_message(
                    chat_id=chat_id,
                    message_id=query.message.id,
                    text_html=text,
                    reply_markup=styled_kb_dict,
                )
                if not edited:
                    await safe_tg_call(query.message.edit_text, text=text, reply_markup=pyro_markup)
            await query.answer()
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
            text, pyro_markup, styled_kb_dict = build_seek_score_view(
                score_data=score_data,
                target_id=target_id,
                target_name=user.first_name if target_id == user.id else "Player",
                search_key=s_key,
                time_key=t_key,
                word_length=w_len,
            )
            if query.message:
                edited = await edit_styled_message(
                    chat_id=chat_id,
                    message_id=query.message.id,
                    text_html=text,
                    reply_markup=styled_kb_dict,
                )
                if not edited:
                    await safe_tg_call(query.message.edit_text, text=text, reply_markup=pyro_markup)
            await query.answer()


# ============================================================================
# WORDSEEK TEXT GUESS HANDLER — BOT API 10.3 RICH MESSAGE (<tg-button> ONLY!)
# ============================================================================
@Client.on_message(
    filters.text
    & ~filters.bot
    & ~bot_command(ALL_KNOWN_COMMANDS),
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
                "Your previous game has expired. Please start today's WordSeek with /daily",
            )
            return

        if not is_valid_seek_guess(raw_text, 5):
            await safe_tg_call(
                message.reply_text,
                f"{raw_text.upper()} is not a valid word.",
                quote=True,
            )
            return

        existing_docs = await get_daily_guesses(user.id, today_str)
        guesses = [d["guess"] for d in existing_docs]
        if raw_text in guesses:
            await safe_tg_call(
                message.reply_text,
                "You've already guessed this word. Try a different one!",
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
                [[make_button("Share", switch_inline_query=share_txt, icon_id=ID_SHARE, fallback_prefix="📤")]]
            )
            await safe_tg_call(
                message.reply_photo,
                photo=img_io,
                caption=(
                    f"{E_BEST} <b>Congratulations!</b> You solved it in <b>{len(guesses)}</b> {'try' if len(guesses) == 1 else 'tries'}!\n\n"
                    f"{E_BOLT} <b>Current Streak:</b> <code>{curr_s}</code>\n"
                    f"{E_CROWN} <b>Highest Streak:</b> <code>{high_s}</code>\n\n"
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
                [[make_button("Share", switch_inline_query=share_txt, icon_id=ID_SHARE, fallback_prefix="📤")]]
            )
            await safe_tg_call(
                message.reply_photo,
                photo=img_io,
                caption=(
                    f"Game Over! The word was: {target_w.upper()}\n\n"
                    f"💔 Streak reset to 0\n\n"
                    f"{format_word_details(target_w, daily_doc)}\n\n"
                    f"Come back tomorrow for a new challenge!"
                ),
                reply_markup=markup,
            )
            return

        rem = 6 - len(guesses)
        await safe_tg_call(
            message.reply_photo,
            photo=img_io,
            caption=f"{rem} {'attempt' if rem == 1 else 'attempts'} remaining",
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
            f"{raw_text} is not a valid {wlen}-letter word.",
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
                "Someone has already guessed your word. Please try another one!",
                quote=True,
            )
            return

        target_w = game["word"].lower()

        if raw_text == target_w:
            prev_guesses_count = len(game["guesses"])
            score = max(1, WORDSEEK_MAX_GUESSES - prev_guesses_count)
            active_seek_games.pop(session_key, None)

            await add_seek_score(
                user_id=user.id,
                first_name=user.first_name,
                username=user.username,
                chat_id=chat_id,
                score=score,
                word_length=wlen,
            )

            formatted_response = (
                f"{E_ANIME_COOL} <b>Correct Guess!</b>\n"
                f"<blockquote>{E_VERIFIED} Word: <b>{raw_text.upper()}</b>\n"
                f"{E_BEST} Reward: <b>+{score} pts</b> added to leaderboard</blockquote>\n"
                f"{E_NEW} Start next round with <code>/new{wlen}</code>"
            )
            await safe_tg_call(
                message.reply_text,
                formatted_response,
                quote=True,
            )
            try:
                await message.react("🎉")
            except Exception:
                pass
            return

        game["guessed_set"].add(raw_text)
        game["guesses"].append(raw_text)
        all_guesses = list(game["guesses"])

        if len(all_guesses) >= WORDSEEK_MAX_GUESSES:
            active_seek_games.pop(session_key, None)
            await safe_tg_call(
                message.reply_text,
                f"{E_STOP} <b>Game Over!</b>\n<blockquote>{E_VERIFIED} The word was <b>{target_w.upper()}</b></blockquote>\n{E_NEW} Start a new game with <code>/new{wlen}</code>",
            )
            return

    # Send Bot API 10.3 RichMessage (`sendRichMessage`) where ONLY `<tg-button>` colored letter buttons appear!
    rich_html = build_rich_feedback(all_guesses, target_w, WORDSEEK_MAX_GUESSES)
    sent = await send_rich_message(
        chat_id=chat_id,
        html_content=rich_html,
        message_thread_id=topic_id if topic_id != "general" else None,
    )
    if not sent:
        # Fallback if a custom Bot API root doesn't support sendRichMessage
        fallback_rows = "\n".join(format_guess_emoji_row(g, target_w) for g in all_guesses)
        await safe_tg_call(
            message.reply_text,
            f"<b>{wlen}-letter mode</b> (<i>{len(all_guesses)}/{WORDSEEK_MAX_GUESSES} guesses</i>)\n<blockquote>{fallback_rows}</blockquote>",
        )
