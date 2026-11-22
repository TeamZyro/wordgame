import os
import time
import platform
import asyncio
import logging
from pyrogram import Client, filters
from pyrogram.types import Message, CallbackQuery
from pyrogram.errors import FloodWait
from bot.config import SUDO_USERS, CALLBACK_COOLDOWN
from bot.database import db
from bot.plugins.game import active_games
from bot.plugins.wordseek import active_seek_games
from bot.utils.cooldown import check_cooldown, safe_tg_call
from bot.utils.command_filter import bot_command
from bot.utils.views import build_admin_view, normalize_fancy_telegram_name
from bot.utils.emojis import (
    E_ROBOT, E_STATS, E_USER, E_CHAT, E_GRID, E_GAME, E_CLOCK24,
    E_SETTINGS, E_VERIFIED, E_BAN, E_MEGAPHONE, E_CROSS, E_WARN, E_BOLT,
)

logger = logging.getLogger("WordGridBot.Admin")
BOT_START_TIME = time.monotonic()


@Client.on_message(bot_command(["panel", "admin"]) & filters.user(SUDO_USERS))
async def admin_panel(client: Client, message: Message):
    text, markup = build_admin_view(section="home")
    await safe_tg_call(message.reply_text, text, reply_markup=markup)


@Client.on_message(bot_command(["stats"]) & filters.user(SUDO_USERS))
async def stats_command(client: Client, message: Message):
    total_users = await db.get_total_users(force_refresh=True)
    total_groups = await db.get_total_groups(force_refresh=True)
    running_grid = sum(1 for g in active_games.values() if not g.get("solved", True))
    running_seek = len(active_seek_games)

    uptime_sec = int(time.monotonic() - BOT_START_TIME)
    hours, rem = divmod(uptime_sec, 3600)
    minutes, seconds = divmod(rem, 60)

    text = (
        f"{E_ROBOT} <b>Word Arcade &amp; WordSeek — System Stats</b>\n\n"
        "<blockquote>"
        f"{E_STATS} <b>Bot Overview</b>\n"
        f"├ {E_USER} Total Users: <code>{total_users:,}</code>\n"
        f"├ {E_CHAT} Total Groups: <code>{total_groups:,}</code>\n"
        f"├ {E_GRID} Active Grid Games: <code>{running_grid}</code>\n"
        f"├ {E_GAME} Active Seek Games: <code>{running_seek}</code>\n"
        f"└ {E_CLOCK24} Uptime: <code>{hours}h {minutes}m {seconds}s</code>"
        "</blockquote>\n"
        "<blockquote>"
        f"{E_SETTINGS} <b>Runtime Environment</b>\n"
        f"├ {E_BOLT} Python: <code>{platform.python_version()}</code>\n"
        f"├ {E_ROBOT} OS: <code>{platform.system()} {platform.machine()}</code>\n"
        f"└ {E_GRID} PID: <code>{os.getpid()}</code>"
        "</blockquote>"
    )
    await safe_tg_call(message.reply_text, text, quote=True)


@Client.on_message(bot_command(["ban", "unban", "transfer"]) & filters.user(SUDO_USERS))
async def moderation_commands(client: Client, message: Message):
    cmd = message.command[0].lower()
    args = message.command[1:] if message.command and len(message.command) > 1 else []

    if cmd == "transfer":
        if len(args) < 2 or not args[0].lstrip("-").isdigit() or not args[1].lstrip("-").isdigit():
            await safe_tg_call(
                message.reply_text,
                f"{E_WARN} <b>Usage:</b> <code>/transfer &lt;from_user_id&gt; &lt;to_user_id&gt;</code>",
                quote=True,
            )
            return
        from_id, to_id = int(args[0]), int(args[1])
        count = await db.transfer_seek_scores(from_id, to_id)
        await safe_tg_call(
            message.reply_text,
            f"{E_VERIFIED} <b>Transferred <code>{count}</code> WordSeek score records from <code>{from_id}</code> to <code>{to_id}</code>.</b>",
            quote=True,
        )
        return

    target_id = None
    if message.reply_to_message and message.reply_to_message.from_user:
        target_id = message.reply_to_message.from_user.id
    elif args:
        doc = await db.find_user_by_username_or_id(args[0])
        if doc:
            target_id = int(doc["user_id"])
        elif args[0].lstrip("-").isdigit():
            target_id = int(args[0])

    if not target_id:
        await safe_tg_call(
            message.reply_text,
            f"{E_WARN} <b>Usage:</b> Reply to a user or send <code>/{cmd} [user_id or @username]</code>",
            quote=True,
        )
        return

    if cmd == "ban":
        await db.ban_user(target_id)
        await safe_tg_call(message.reply_text, f"{E_BAN} <b>Banned user <code>{target_id}</code> globally.</b>", quote=True)
    else:
        await db.unban_user(target_id)
        await safe_tg_call(message.reply_text, f"{E_VERIFIED} <b>Unbanned user <code>{target_id}</code>.</b>", quote=True)


@Client.on_callback_query(filters.regex(r"^admin[:_]") & filters.user(SUDO_USERS))
async def admin_callbacks(client: Client, query: CallbackQuery):
    user = query.from_user
    if user:
        allowed, wait_sec = check_cooldown(f"cb:admin:{user.id}", CALLBACK_COOLDOWN)
        if not allowed:
            await query.answer(f"⏳ Wait {wait_sec}s!", show_alert=False)
            return

    data = query.data.replace("admin_", "admin:")

    if data == "admin:stats":
        total_users = await db.get_total_users(force_refresh=True)
        total_groups = await db.get_total_groups(force_refresh=True)
        running_grid = sum(1 for g in active_games.values() if not g.get("solved", True))
        running_seek = len(active_seek_games)
        text, markup = build_admin_view(
            section="stats",
            total_users=total_users,
            total_groups=total_groups,
            active_grid_games=running_grid,
            active_seek_games=running_seek,
        )
        await safe_tg_call(query.message.edit_text, text, reply_markup=markup)
        await query.answer("📊 Stats updated!")

    elif data == "admin:home":
        text, markup = build_admin_view(section="home")
        await safe_tg_call(query.message.edit_text, text, reply_markup=markup)
        await query.answer()

    elif data == "admin:broadcast":
        text, markup = build_admin_view(section="broadcast")
        await safe_tg_call(query.message.edit_text, text, reply_markup=markup)
        await query.answer()


@Client.on_message(bot_command("broadcast") & filters.user(SUDO_USERS) & filters.reply)
async def broadcast_command(client: Client, message: Message):
    msg_to_broadcast = message.reply_to_message
    if not msg_to_broadcast:
        return

    users = await db.get_all_users()
    groups = await db.get_all_groups()
    total_targets = len(users) + len(groups)

    status_msg = await safe_tg_call(
        message.reply_text,
        (
            f"{E_MEGAPHONE} <b>Starting Broadcast...</b>\n\n"
            f"<blockquote>"
            f"{E_USER} <b>Users:</b> <code>{len(users)}</code>\n"
            f"{E_CHAT} <b>Groups:</b> <code>{len(groups)}</code>\n"
            f"{E_BOLT} <b>Total Targets:</b> <code>{total_targets}</code>"
            f"</blockquote>"
        ),
    )

    user_success = 0
    group_success = 0
    failed = 0

    async def _copy_safe(chat_id: int) -> bool:
        for _ in range(2):
            try:
                await msg_to_broadcast.copy(chat_id)
                return True
            except FloodWait as e:
                wait_s = int(getattr(e, "value", getattr(e, "x", 5)))
                await asyncio.sleep(min(wait_s + 1, 30))
            except Exception:
                return False
        return False

    for user in users:
        uid = user.get("user_id")
        if uid and await _copy_safe(uid):
            user_success += 1
        else:
            failed += 1
        await asyncio.sleep(0.06)

    for group in groups:
        cid = group.get("chat_id")
        if cid and await _copy_safe(cid):
            group_success += 1
        else:
            failed += 1
        await asyncio.sleep(0.06)

    summary = (
        f"{E_VERIFIED} <b>Broadcast Completed!</b>\n\n"
        "<blockquote>"
        f"{E_USER} <b>Users Reached:</b> <code>{user_success}/{len(users)}</code>\n"
        f"{E_CHAT} <b>Groups Reached:</b> <code>{group_success}/{len(groups)}</code>\n"
        f"{E_CROSS} <b>Failed / Blocked:</b> <code>{failed}</code>"
        "</blockquote>"
    )
    if status_msg:
        await safe_tg_call(status_msg.edit_text, summary)
    else:
        await safe_tg_call(message.reply_text, summary)
