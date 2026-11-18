import asyncio
import logging
from pyrogram import Client, filters
from pyrogram.types import Message, CallbackQuery
from pyrogram.errors import FloodWait
from bot.config import SUDO_USERS, CALLBACK_COOLDOWN
from bot.database import db
from bot.plugins.game import active_games
from bot.utils.cooldown import check_cooldown, safe_tg_call
from bot.utils.views import build_admin_view

logger = logging.getLogger("WordGridBot.Admin")


@Client.on_message(filters.command(["panel", "admin"]) & filters.user(SUDO_USERS))
async def admin_panel(client: Client, message: Message):
    text, markup = build_admin_view(section="home")
    await safe_tg_call(message.reply_text, text, reply_markup=markup)


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
        running_games = sum(1 for g in active_games.values() if not g.get("solved", True))
        text, markup = build_admin_view(
            section="stats",
            total_users=total_users,
            total_groups=total_groups,
            active_games_count=running_games,
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


@Client.on_message(filters.command("broadcast") & filters.user(SUDO_USERS) & filters.reply)
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
            f"📢 <b>Starting Broadcast...</b>\n\n"
            f"<blockquote>"
            f"👤 <b>Users:</b> <code>{len(users)}</code>\n"
            f"👥 <b>Groups:</b> <code>{len(groups)}</code>\n"
            f"🎯 <b>Total Targets:</b> <code>{total_targets}</code>"
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
        "✅ <b>Broadcast Completed!</b>\n\n"
        "<blockquote>"
        f"👤 <b>Users Reached:</b> <code>{user_success}/{len(users)}</code>\n"
        f"👥 <b>Groups Reached:</b> <code>{group_success}/{len(groups)}</code>\n"
        f"❌ <b>Failed / Blocked:</b> <code>{failed}</code>"
        "</blockquote>"
    )
    if status_msg:
        await safe_tg_call(status_msg.edit_text, summary)
    else:
        await safe_tg_call(message.reply_text, summary)
