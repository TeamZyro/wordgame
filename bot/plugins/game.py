import time
import uuid
import asyncio
import logging
import random
from pyrogram import Client, filters
from pyrogram.types import Message, InputMediaPhoto, CallbackQuery
from pyrogram.enums import ChatType
from bot.utils.image_gen import create_new_game_state, render_grid_image, create_single_hint
from bot.utils.views import (
    build_game_caption,
    build_game_board_markup,
    build_leaderboard_view,
    build_seek_leaderboard_view,
    normalize_fancy_telegram_name,
)
from bot.utils.rich_api import send_styled_message
from bot.utils.command_filter import bot_command
from bot.utils.emojis import (
    E_GAME, E_GRID, E_TIMER, E_SEARCH, E_LOOP, E_LOADING, E_CROSS,
    E_WARN, E_STOP, E_CLOVER, E_HOURGLASS, E_VERIFIED, E_BEST, E_LEVELUP, E_BOLT,
)
from bot.utils.cooldown import (
    check_cooldown,
    get_chat_lock,
    get_user_lock,
    safe_tg_call,
)
from bot.database.db import (
    add_score,
    get_top_users,
    add_group_score,
    get_top_groups,
    add_group,
    get_seek_leaderboard,
    is_user_banned,
)
from bot.config import (
    CMD_COOLDOWN,
    GAME_START_COOLDOWN,
    HINT_COOLDOWN,
    REFRESH_COOLDOWN,
    CALLBACK_COOLDOWN,
    GUESS_COOLDOWN,
    MAX_HINTS_PER_ROUND,
)

logger = logging.getLogger("WordGridBot.Game")

active_games: dict[int, dict] = {}
group_rounds: dict[int, int] = {}

ALL_KNOWN_COMMANDS = [
    "game", "stopgame", "hint", "panel", "admin", "broadcast",
    "leaderboard", "top", "start", "help", "profile", "rank",
    "stats", "me", "wordseek", "new", "new4", "new5", "new6",
    "end", "endseek", "daily", "pausedaily", "score", "myscore",
    "seekauth", "setgametopic", "unsetgametopic", "allowonlylen",
    "id", "ban", "unban", "transfer",
]


def get_round_difficulty(round_num: int) -> tuple[int, int]:
    if round_num <= 2:
        return 3, 45
    if round_num <= 4:
        return 4, 55
    if round_num <= 7:
        return 5, 65
    if round_num <= 11:
        return 6, 75
    if round_num <= 16:
        return 7, 85
    if round_num <= 22:
        return 8, 95
    if round_num <= 28:
        return 9, 110
    if round_num <= 35:
        return 10, 120
    if round_num <= 42:
        return 11, 135
    if round_num <= 50:
        return 12, 150
    return 13, 165


def cancel_game_tasks(chat_id: int) -> None:
    game = active_games.get(chat_id)
    if not game:
        return
    for task_key in ("timeout_task", "next_round_task", "media_update_task"):
        task = game.get(task_key)
        if task and isinstance(task, asyncio.Task) and not task.done():
            task.cancel()


async def _update_board_media(client: Client, chat_id: int, game: dict, status_banner: str | None = None):
    try:
        updated_img_io = await asyncio.to_thread(
            render_grid_image,
            grid=game["grid"],
            words_info=game["words_info"],
            found_words=game["found_words"],
            round_num=game["round"],
            theme_name=game["theme"],
        )
        caption = build_game_caption(game, status_banner=status_banner)
        markup = build_game_board_markup(solved=game.get("solved", False))
        media = InputMediaPhoto(media=updated_img_io, caption=caption)
        await safe_tg_call(
            client.edit_message_media,
            chat_id=chat_id,
            message_id=game["message_id"],
            media=media,
            reply_markup=markup,
        )
        game["last_media_edit"] = time.monotonic()
    except Exception as e:
        logger.debug("Board media update fallback to caption edit: %s", e)
        await safe_tg_call(
            client.edit_message_caption,
            chat_id=chat_id,
            message_id=game["message_id"],
            caption=build_game_caption(game, status_banner=status_banner),
            reply_markup=build_game_board_markup(solved=game.get("solved", False)),
        )


async def _debounced_board_update(client: Client, chat_id: int, game_id: str, delay: float = 1.2):
    try:
        await asyncio.sleep(delay)
        async with get_chat_lock(chat_id):
            game = active_games.get(chat_id)
            if not game or game.get("game_id") != game_id or game.get("solved"):
                return
            await _update_board_media(client, chat_id, game)
    except asyncio.CancelledError:
        pass


async def game_timeout_monitor(client: Client, chat_id: int, game_id: str, round_num: int, duration: float):
    try:
        await asyncio.sleep(duration)
    except asyncio.CancelledError:
        return

    async with get_chat_lock(chat_id):
        game = active_games.get(chat_id)
        if not game or game.get("game_id") != game_id or game.get("solved"):
            return

        game["solved"] = True
        group_rounds[chat_id] = 1

        missed = [w for w, info in game["words"].items() if not info.get("found_by")]
        missed_str = ", ".join(f"<code>{w}</code>" for w in missed) if missed else "None"

        timeout_banner = (
            f"{E_TIMER} <b>TIME UP! Round {round_num} Expired.</b>\n"
            f"{E_SEARCH} <b>Missed:</b> {missed_str}\n"
            f"{E_LOOP} <i>Streak reset to Round 1. Tap <b>Play Again</b> or send <code>/game</code>!</i>"
        )

    await safe_tg_call(
        client.edit_message_caption,
        chat_id=chat_id,
        message_id=game["message_id"],
        caption=build_game_caption(game, status_banner=timeout_banner),
        reply_markup=build_game_board_markup(solved=True),
    )

    await safe_tg_call(
        client.send_message,
        chat_id,
        (
            f"{E_TIMER} <b>ROUND {round_num} — TIME UP!</b>\n\n"
            f"<blockquote>"
            f"{E_SEARCH} <b>Unfound Words:</b> {missed_str}\n"
            f"{E_LOOP} <b>Streak:</b> Reset to <b>Round 1</b>"
            f"</blockquote>\n"
            f"{E_GAME} Tap below or send <code>/game</code> to play again!"
        ),
        reply_markup=build_game_board_markup(solved=True),
    )


async def execute_round(client: Client, chat_id: int, status_message: Message | None = None):
    async with get_chat_lock(chat_id):
        cancel_game_tasks(chat_id)

        if len(active_games) > 300:
            solved_chats = [cid for cid, g in active_games.items() if g.get("solved")]
            for cid in solved_chats[:150]:
                active_games.pop(cid, None)

        round_num = group_rounds.get(chat_id, 1)
        word_count, time_limit = get_round_difficulty(round_num)

        if status_message is None:
            status_message = await safe_tg_call(
                client.send_message,
                chat_id,
                f"{E_LOADING} <b>Generating Round {round_num} Word Grid...</b>",
            )
        else:
            await safe_tg_call(
                status_message.edit_text,
                f"{E_LOADING} <b>Generating Round {round_num} Word Grid...</b>",
            )

        grid, words_info, theme_name = await asyncio.to_thread(
            create_new_game_state, word_count, round_num
        )
        if not words_info:
            if status_message:
                await safe_tg_call(
                    status_message.edit_text,
                    f"{E_CROSS} <b>Could not build puzzle board. Please try <code>/game</code> again.</b>",
                )
            return

        words_dict = {}
        for w in words_info.keys():
            w_upper = w.upper()
            words_dict[w_upper] = {
                "hint": create_single_hint(w_upper),
                "revealed": set(),
                "found_by": None,
                "points": 0,
            }

        game_id = uuid.uuid4().hex
        game_data = {
            "game_id": game_id,
            "round": round_num,
            "grid": grid,
            "words_info": words_info,
            "words": words_dict,
            "found_words": [],
            "round_scores": {},
            "hints_used": 0,
            "max_hints": MAX_HINTS_PER_ROUND,
            "solved": False,
            "start_time": time.monotonic(),
            "last_media_edit": 0.0,
            "time_limit": time_limit,
            "theme": theme_name,
            "message_id": None,
            "timeout_task": None,
            "next_round_task": None,
            "media_update_task": None,
        }

        img_io = await asyncio.to_thread(
            render_grid_image,
            grid,
            words_info,
            game_data["found_words"],
            round_num=round_num,
            theme_name=theme_name,
        )
        caption_text = build_game_caption(game_data)
        markup = build_game_board_markup(solved=False)

        if status_message:
            await safe_tg_call(status_message.delete)

        msg = await safe_tg_call(
            client.send_photo,
            chat_id=chat_id,
            photo=img_io,
            caption=caption_text,
            reply_markup=markup,
        )
        if not msg:
            return

        game_data["start_time"] = time.monotonic()
        game_data["last_media_edit"] = time.monotonic()
        game_data["message_id"] = msg.id
        game_data["timeout_task"] = asyncio.create_task(
            game_timeout_monitor(client, chat_id, game_id, round_num, time_limit)
        )
        active_games[chat_id] = game_data


async def _auto_advance_round(client: Client, chat_id: int, expected_game_id: str, delay: float = 3.0):
    try:
        await asyncio.sleep(delay)
        game = active_games.get(chat_id)
        if not game or game.get("game_id") != expected_game_id:
            return
        await execute_round(client, chat_id)
    except asyncio.CancelledError:
        return


@Client.on_message(bot_command(["game", "stopgame", "hint"]))
async def game_commands(client: Client, message: Message):
    user = message.from_user
    if user and await is_user_banned(user.id):
        return

    if message.chat.type == ChatType.PRIVATE:
        await safe_tg_call(
            message.reply_text,
            (
                f"{E_WARN} <b>Word Grid is for Groups!</b>\n\n"
                "<blockquote>Add me to a group for 3D Word Grid (<code>/game</code>), "
                "or play <b>WordSeek</b> right here in DM using <code>/new</code> or <code>/daily</code>!</blockquote>"
            ),
            quote=True,
        )
        return

    chat_id = message.chat.id
    cmd = message.command[0].lower()

    if user:
        allowed, _ = check_cooldown(f"cmd:{cmd}:{user.id}", CMD_COOLDOWN)
        if not allowed:
            return

    if cmd == "stopgame":
        async with get_chat_lock(chat_id):
            game = active_games.get(chat_id)
            if game and not game.get("solved", True):
                game["solved"] = True
                cancel_game_tasks(chat_id)
                group_rounds[chat_id] = 1
                stopped_round = game.get("round", 1)
                await safe_tg_call(
                    client.edit_message_caption,
                    chat_id=chat_id,
                    message_id=game["message_id"],
                    caption=build_game_caption(
                        game,
                        status_banner=f"{E_STOP} <b>Game stopped. Progress reset to Round 1.</b>",
                    ),
                    reply_markup=build_game_board_markup(solved=True),
                )
                await safe_tg_call(
                    message.reply_text,
                    f"{E_STOP} <b>Round {stopped_round} Stopped!</b>\n<i>Progress reset to Round 1. Send <code>/game</code> to play again.</i>",
                )
            else:
                cancel_game_tasks(chat_id)
                await safe_tg_call(
                    message.reply_text,
                    f"{E_GRID} <b>No active Word Grid game running.</b>\n<i>Send <code>/game</code> to start Round 1!</i>",
                )
        return

    if cmd == "hint":
        await _handle_hint_request(client, chat_id, message=message)
        return

    allowed_chat, chat_wait = check_cooldown(f"chat:gamestart:{chat_id}", GAME_START_COOLDOWN)
    if not allowed_chat:
        await safe_tg_call(
            message.reply_text,
            f"{E_HOURGLASS} <b>Wait {chat_wait}s before starting a new round!</b>",
        )
        return

    async with get_chat_lock(chat_id):
        if chat_id in active_games:
            active = active_games[chat_id]
            if not active.get("solved", True):
                time_elapsed = time.monotonic() - active["start_time"]
                if time_elapsed < active["time_limit"]:
                    time_left = max(1, int(active["time_limit"] - time_elapsed))
                    await safe_tg_call(
                        message.reply_text,
                        (
                            f"{E_WARN} <b>Round {active['round']} is already running!</b>\n"
                            f"{E_TIMER} <b>Remaining:</b> <code>{time_left}s</code>  •  Use <code>/stopgame</code> to end."
                        ),
                    )
                    return
                active["solved"] = True
                cancel_game_tasks(chat_id)

        await add_group(chat_id, message.chat.title)
        group_rounds[chat_id] = 1

    m = await safe_tg_call(message.reply_text, f"{E_GRID} <b>Starting Word Grid — Round 1...</b>")
    await execute_round(client, chat_id, m)


async def _handle_hint_request(
    client: Client,
    chat_id: int,
    message: Message | None = None,
    query: CallbackQuery | None = None,
):
    async with get_chat_lock(chat_id):
        game = active_games.get(chat_id)
        if not game or game.get("solved", True):
            if query:
                await query.answer("⚠️ No active Word Grid running!", show_alert=True)
            elif message:
                await safe_tg_call(
                    message.reply_text,
                    f"{E_WARN} <b>No active Word Grid running!</b> Send <code>/game</code> to start.",
                )
            return

        if game["hints_used"] >= game["max_hints"]:
            msg_txt = f"⚠️ Max hints ({game['max_hints']}/{game['max_hints']}) used for Round {game['round']}!"
            if query:
                await query.answer(msg_txt, show_alert=True)
            elif message:
                await safe_tg_call(message.reply_text, f"<b>{msg_txt}</b>")
            return

        allowed, wait_sec = check_cooldown(f"chat:hint:{chat_id}", HINT_COOLDOWN)
        if not allowed:
            msg_txt = f"⏳ Hint cooldown! Wait {wait_sec}s."
            if query:
                await query.answer(msg_txt, show_alert=True)
            elif message:
                await safe_tg_call(message.reply_text, f"<b>{msg_txt}</b>")
            return

        unfound = [w for w, info in game["words"].items() if not info.get("found_by")]
        if not unfound:
            if query:
                await query.answer("✅ All words found!", show_alert=False)
            return

        target_word = random.choice(unfound)
        info = game["words"][target_word]
        revealed: set[int] = info.setdefault("revealed", set())

        wlen = len(target_word)
        default_shown = {0, wlen - 1}
        if wlen >= 6:
            default_shown.add(wlen // 2)
        currently_shown = default_shown | revealed
        hidden_indices = [i for i in range(wlen) if i not in currently_shown]

        if hidden_indices:
            revealed.add(random.choice(hidden_indices))

        info["hint"] = create_single_hint(target_word, revealed)
        game["hints_used"] += 1
        new_hint = info["hint"]
        hints_left = game["max_hints"] - game["hints_used"]

    await safe_tg_call(
        client.edit_message_caption,
        chat_id=chat_id,
        message_id=game["message_id"],
        caption=build_game_caption(game),
        reply_markup=build_game_board_markup(solved=False),
    )

    if query:
        await query.answer(f"💡 Hint: {new_hint} ({hints_left} left)", show_alert=False)
    elif message:
        await safe_tg_call(
            message.reply_text,
            f"{E_CLOVER} <b>Hint:</b> <code>{new_hint}</code> <b>({len(target_word)}L)</b>  •  <i>{hints_left} left</i>",
        )


@Client.on_callback_query(filters.regex(r"^game:"))
async def game_board_callbacks(client: Client, query: CallbackQuery):
    if not query.message or not query.from_user:
        await query.answer()
        return

    user = query.from_user
    if await is_user_banned(user.id):
        await query.answer()
        return

    chat_id = query.message.chat.id
    action = query.data.split(":", 1)[1]

    allowed_cb, cb_wait = check_cooldown(f"cb:game:{user.id}", CALLBACK_COOLDOWN)
    if not allowed_cb:
        await query.answer(f"⏳ Wait {cb_wait}s!", show_alert=False)
        return

    if action == "hint":
        await _handle_hint_request(client, chat_id, query=query)
        return

    if action == "refresh":
        async with get_chat_lock(chat_id):
            game = active_games.get(chat_id)
            if not game or game.get("solved", True):
                await query.answer("⚠️ Round is finished!", show_alert=True)
                return

            allowed_ref, ref_wait = check_cooldown(f"chat:refresh:{chat_id}", REFRESH_COOLDOWN)
            if not allowed_ref:
                await query.answer(f"⏳ Wait {ref_wait}s to refresh board!", show_alert=True)
                return

            img_io = await asyncio.to_thread(
                render_grid_image,
                grid=game["grid"],
                words_info=game["words_info"],
                found_words=game["found_words"],
                round_num=game["round"],
                theme_name=game["theme"],
            )
            old_msg_id = game.get("message_id")
            new_msg = await safe_tg_call(
                client.send_photo,
                chat_id=chat_id,
                photo=img_io,
                caption=build_game_caption(game),
                reply_markup=build_game_board_markup(solved=False),
            )
            if new_msg:
                game["message_id"] = new_msg.id
                if old_msg_id:
                    await safe_tg_call(client.delete_messages, chat_id, old_msg_id)
        await query.answer("🔄 Board moved to bottom!")
        return

    if action == "stop":
        async with get_chat_lock(chat_id):
            game = active_games.get(chat_id)
            if not game or game.get("solved", True):
                await query.answer("ℹ️ Already stopped.", show_alert=False)
                return
            game["solved"] = True
            cancel_game_tasks(chat_id)
            group_rounds[chat_id] = 1
            stopped_by = normalize_fancy_telegram_name(user.first_name, max_len=18)
            await safe_tg_call(
                client.edit_message_caption,
                chat_id=chat_id,
                message_id=game["message_id"],
                caption=build_game_caption(
                    game,
                    status_banner=f"{E_STOP} <b>Stopped by {stopped_by}. Reset to Round 1.</b>",
                ),
                reply_markup=build_game_board_markup(solved=True),
            )
        await query.answer("🛑 Stopped!")
        return

    if action == "new":
        if query.message.chat.type == ChatType.PRIVATE:
            await query.answer("Add me to a group for Word Grid!", show_alert=True)
            return
        allowed_chat, chat_wait = check_cooldown(f"chat:gamestart:{chat_id}", GAME_START_COOLDOWN)
        if not allowed_chat:
            await query.answer(f"⏳ Wait {chat_wait}s!", show_alert=False)
            return

        async with get_chat_lock(chat_id):
            active = active_games.get(chat_id)
            if active and not active.get("solved", True):
                if (time.monotonic() - active["start_time"]) < active["time_limit"]:
                    await query.answer("⚠️ A round is already active!", show_alert=True)
                    return
                active["solved"] = True
                cancel_game_tasks(chat_id)
            group_rounds[chat_id] = 1

        await query.answer("🎮 Launching Round 1!")
        await execute_round(client, chat_id)


@Client.on_message(
    filters.text
    & ~filters.bot
    & ~bot_command(ALL_KNOWN_COMMANDS),
    group=1,
)
async def check_answer(client: Client, message: Message):
    chat_id = message.chat.id
    if chat_id not in active_games:
        return

    game = active_games.get(chat_id)
    if not game or game.get("solved", True) or not message.text or not message.from_user:
        return

    user_word = message.text.strip().upper()
    if user_word not in game["words"]:
        return

    user = message.from_user
    if await is_user_banned(user.id):
        return

    allowed_guess, _ = check_cooldown(f"guess:{chat_id}:{user.id}", GUESS_COOLDOWN)
    if not allowed_guess:
        return

    async with get_chat_lock(chat_id):
        game = active_games.get(chat_id)
        if not game or game.get("solved", True):
            return

        if (time.monotonic() - game["start_time"]) > game["time_limit"]:
            game["solved"] = True
            cancel_game_tasks(chat_id)
            group_rounds[chat_id] = 1
            await safe_tg_call(
                message.reply_text,
                f"{E_TIMER} <b>TIME UP!</b>\nRound {game['round']} expired. Reset to Round 1.\nSend <code>/game</code> to play again!",
                quote=True,
            )
            return

        word_info = game["words"].get(user_word)
        if not word_info:
            return

        if word_info["found_by"] is not None:
            finder_name = normalize_fancy_telegram_name(word_info["found_by"], max_len=18)
            await safe_tg_call(
                message.reply_text,
                f"{E_WARN} <code>{user_word}</code> was already found by <b>{finder_name}</b>!",
                quote=True,
            )
            return

        if len(user_word) <= 4:
            base_points = 1
        elif len(user_word) <= 6:
            base_points = 2
        else:
            base_points = 3
        round_bonus = game["round"] // 10
        points = base_points + round_bonus

        word_info["found_by"] = user.first_name
        word_info["points"] = points
        game["found_words"].append(user_word)

        r_scores = game["round_scores"]
        if user.id not in r_scores:
            r_scores[user.id] = {"name": user.first_name, "pts": 0, "words": 0}
        r_scores[user.id]["pts"] += points
        r_scores[user.id]["words"] += 1

        all_found = all(info["found_by"] is not None for info in game["words"].values())
        if all_found:
            game["solved"] = True
            cancel_game_tasks(chat_id)
            time_taken = max(1, int(time.monotonic() - game["start_time"]))
            cleared_round = game["round"]
            next_round = cleared_round + 1
            group_rounds[chat_id] = next_round
            game_id = game["game_id"]

    await add_score(
        user_id=user.id,
        first_name=user.first_name,
        points=points,
        round_num=game["round"],
        username=user.username,
    )
    await add_group_score(
        chat_id=chat_id,
        title=message.chat.title,
        points=points,
        round_num=game["round"],
    )

    safe_finder = normalize_fancy_telegram_name(user.first_name, max_len=20)

    if all_found:
        cleared_banner = f"{E_BEST} <b>ROUND {cleared_round} CLEARED in {time_taken}s!</b>"
        await _update_board_media(client, chat_id, game, status_banner=cleared_banner)

        mvp_lines = []
        sorted_contributors = sorted(
            game["round_scores"].values(), key=lambda x: (x["pts"], x["words"]), reverse=True
        )
        for idx, c in enumerate(sorted_contributors[:5]):
            c_name = normalize_fancy_telegram_name(c["name"], max_len=18)
            medal = E_BEST if idx == 0 else "•"
            mvp_lines.append(f"{medal} <b>{c_name}:</b> <code>+{c['pts']} pts</code> ({c['words']}w)")
        mvp_block = "\n".join(mvp_lines)

        await safe_tg_call(
            message.reply_text,
            (
                f"{E_VERIFIED} <b>{safe_finder}</b> found <code>{user_word}</code> (<b>+{points} pts</b>)!\n\n"
                f"{E_BEST} <b>ROUND {cleared_round} CLEARED IN {time_taken}s!</b>\n"
                f"<blockquote>{mvp_block}</blockquote>\n"
                f"{E_LEVELUP} <i>Next Round {next_round} in 3 seconds...</i>"
            ),
        )

        async with get_chat_lock(chat_id):
            if chat_id in active_games and active_games[chat_id].get("game_id") == game_id:
                active_games[chat_id]["next_round_task"] = asyncio.create_task(
                    _auto_advance_round(client, chat_id, game_id, delay=3.0)
                )
    else:
        rem = sum(1 for info in game["words"].values() if info["found_by"] is None)
        await safe_tg_call(
            message.reply_text,
            f"{E_VERIFIED} <b>{safe_finder}</b> found <code>{user_word}</code>! (<b>+{points} pts</b>)  •  <i>{rem} left</i>",
            quote=True,
        )

        now = time.monotonic()
        async with get_chat_lock(chat_id):
            prev_task = game.get("media_update_task")
            if prev_task and isinstance(prev_task, asyncio.Task) and not prev_task.done():
                prev_task.cancel()

            if (now - game.get("last_media_edit", 0.0)) >= 1.5:
                await _update_board_media(client, chat_id, game)
            else:
                game["media_update_task"] = asyncio.create_task(
                    _debounced_board_update(client, chat_id, game["game_id"], delay=1.2)
                )


def _parse_leaderboard_args(args: list[str], is_private: bool) -> tuple[bool, str, str, int]:
    """
    Parses `/leaderboard [scope] [period] [length]` arguments.
    By default, `/leaderboard` opens WordSeek's styled leaderboard (with a 1-tap toggle to Word Grid),
    or Word Grid if `grid` is passed.
    """
    search_key = "global" if is_private else "group"
    time_key = "today" if not is_private else "all"
    word_length = 5
    is_grid = False

    for raw in args:
        tok = raw.strip().lower()
        if tok in ("grid", "wordgrid"):
            is_grid = True
        elif tok in ("global", "group", "chat"):
            search_key = "group" if tok in ("group", "chat") else "global"
        elif tok in ("today", "week", "month", "year", "all"):
            time_key = tok
        elif tok in ("4", "5", "6", "4l", "5l", "6l"):
            word_length = int(tok[0])

    return not is_grid, search_key, time_key, word_length


@Client.on_message(bot_command(["leaderboard", "top"]))
async def leaderboard_command(client: Client, message: Message):
    user = message.from_user
    if user:
        if await is_user_banned(user.id):
            return
        allowed, _ = check_cooldown(f"cmd:lb:{user.id}", CMD_COOLDOWN)
        if not allowed:
            return

    is_private = message.chat.type == ChatType.PRIVATE
    args = message.command[1:] if message.command and len(message.command) > 1 else []
    use_seek, s_key, t_key, w_len = _parse_leaderboard_args(args, is_private)

    if use_seek:
        entries = await get_seek_leaderboard(
            chat_id=message.chat.id,
            search_key=s_key,
            time_key=t_key,
            word_length=w_len,
        )
        text, pyro_markup, styled_kb_dict = build_seek_leaderboard_view(
            entries=entries,
            search_key=s_key,
            time_key=t_key,
            word_length=w_len,
            show_back=is_private,
        )
        sent = await send_styled_message(
            chat_id=message.chat.id,
            text_html=text,
            reply_markup=styled_kb_dict,
            message_thread_id=getattr(message, "message_thread_id", None),
        )
        if not sent:
            await safe_tg_call(message.reply_text, text, reply_markup=pyro_markup)
        return

    top_users = await get_top_users(10)
    text, markup = build_leaderboard_view(
        mode="users",
        entries=top_users,
        show_back=is_private,
    )
    await safe_tg_call(message.reply_text, text, reply_markup=markup)


@Client.on_callback_query(filters.regex(r"^(leaderboard_|lb:)"))
async def leaderboard_callback(client: Client, query: CallbackQuery):
    user = query.from_user
    if not user or await is_user_banned(user.id):
        await query.answer()
        return

    allowed, wait_sec = check_cooldown(f"cb:lb:{user.id}", CALLBACK_COOLDOWN)
    if not allowed:
        await query.answer(f"⏳ Wait {wait_sec}s!", show_alert=False)
        return

    async with get_user_lock(user.id):
        data = query.data
        force_refresh = data.startswith("lb:refresh:")
        is_groups = "groups" in data

        if is_groups:
            entries = await get_top_groups(10, force_refresh=force_refresh)
            mode = "groups"
        else:
            entries = await get_top_users(10, force_refresh=force_refresh)
            mode = "users"

        show_back = bool(
            query.message
            and (query.message.chat.type == ChatType.PRIVATE or query.message.photo)
        )
        text, markup = build_leaderboard_view(
            mode=mode,
            entries=entries,
            show_back=show_back,
        )

        if (
            query.message
            and query.message.photo
            and "WORD GRID — ROUND" in (query.message.caption or "")
        ):
            await safe_tg_call(query.message.reply_text, text=text, reply_markup=markup)
            await query.answer()
            return

        if query.message and query.message.photo:
            await safe_tg_call(query.message.edit_caption, caption=text, reply_markup=markup)
        elif query.message:
            await safe_tg_call(query.message.edit_text, text=text, reply_markup=markup)

        await query.answer("🔄 Updated!" if force_refresh else "")
