import os
import logging
from pyrogram import Client, filters
from pyrogram.types import Message, CallbackQuery
from pyrogram.enums import ChatType
from bot.database.db import (
    add_user,
    add_group,
    get_user,
    get_user_rank,
    get_top_users,
    get_top_groups,
)
from bot.config import CMD_COOLDOWN, CALLBACK_COOLDOWN
from bot.utils.cooldown import check_cooldown, get_user_lock, safe_tg_call
from bot.utils.views import (
    build_start_view,
    build_help_view,
    build_profile_view,
    build_leaderboard_view,
)

logger = logging.getLogger("WordGridBot.Start")

START_IMG_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), "utils", "start_img.png")
_CACHED_START_FILE_ID: str | None = None


async def _send_start_media_or_text(client: Client, message: Message, text: str, markup):
    """Sends bundled start_img.png with Telegram file_id caching so Heroku uses zero extra disk/bandwidth."""
    global _CACHED_START_FILE_ID
    if _CACHED_START_FILE_ID:
        sent = await safe_tg_call(
            message.reply_photo,
            photo=_CACHED_START_FILE_ID,
            caption=text,
            reply_markup=markup,
        )
        if sent:
            return sent

    if os.path.exists(START_IMG_PATH):
        sent = await safe_tg_call(
            message.reply_photo,
            photo=START_IMG_PATH,
            caption=text,
            reply_markup=markup,
        )
        if sent and getattr(sent, "photo", None):
            _CACHED_START_FILE_ID = sent.photo.file_id
            return sent

    return await safe_tg_call(message.reply_text, text, reply_markup=markup)


async def _edit_or_reply(query: CallbackQuery, text: str, markup):
    """Edits caption if message has photo, otherwise edits text — preserving 100% view consistency."""
    if query.message and query.message.photo:
        return await safe_tg_call(
            query.message.edit_caption,
            caption=text,
            reply_markup=markup,
        )
    if query.message:
        return await safe_tg_call(
            query.message.edit_text,
            text=text,
            reply_markup=markup,
        )
    return None


@Client.on_message(filters.command(["start"]))
async def start_command(client: Client, message: Message):
    user = message.from_user
    if user:
        allowed, _ = check_cooldown(f"cmd:start:{user.id}", CMD_COOLDOWN)
        if not allowed:
            return

    uname = getattr(client.me, "username", None) or "WordGridGameBot"

    if message.chat.type == ChatType.PRIVATE:
        if user:
            await add_user(user.id, user.username, user.first_name)
        text, markup = build_start_view(
            first_name=user.first_name if user else "Player",
            bot_username=uname,
            is_private=True,
        )
        await _send_start_media_or_text(client, message, text, markup)
    else:
        await add_group(message.chat.id, message.chat.title)
        text, markup = build_start_view(
            first_name=user.first_name if user else "Player",
            bot_username=uname,
            is_private=False,
        )
        await safe_tg_call(message.reply_text, text, reply_markup=markup)


@Client.on_message(filters.command(["help"]))
async def help_command(client: Client, message: Message):
    user = message.from_user
    if user:
        allowed, _ = check_cooldown(f"cmd:help:{user.id}", CMD_COOLDOWN)
        if not allowed:
            return

    uname = getattr(client.me, "username", None) or "WordGridGameBot"
    text, markup = build_help_view(bot_username=uname, show_back=True)

    if message.chat.type == ChatType.PRIVATE:
        await _send_start_media_or_text(client, message, text, markup)
    else:
        await safe_tg_call(message.reply_text, text, reply_markup=markup)


@Client.on_message(filters.command(["profile", "rank", "stats", "me"]))
async def profile_command(client: Client, message: Message):
    user = message.from_user
    if not user:
        return
    allowed, wait_sec = check_cooldown(f"cmd:profile:{user.id}", CMD_COOLDOWN)
    if not allowed:
        return

    await add_user(user.id, user.username, user.first_name)
    user_doc = await get_user(user.id)
    rank = await get_user_rank(user.id)
    text, markup = build_profile_view(
        user_id=user.id,
        first_name=user.first_name,
        user_doc=user_doc,
        rank=rank,
        show_back=(message.chat.type == ChatType.PRIVATE),
    )
    await safe_tg_call(message.reply_text, text, reply_markup=markup)


@Client.on_callback_query(filters.regex(r"^(nav:|profile:)"))
async def navigation_callbacks(client: Client, query: CallbackQuery):
    user = query.from_user
    if not user:
        await query.answer()
        return

    allowed, wait_sec = check_cooldown(f"cb:nav:{user.id}", CALLBACK_COOLDOWN)
    if not allowed:
        await query.answer(f"⏳ Please wait {wait_sec}s!", show_alert=False)
        return

    async with get_user_lock(user.id):
        data = query.data
        uname = getattr(client.me, "username", None) or "WordGridGameBot"
        is_private = bool(query.message and query.message.chat.type == ChatType.PRIVATE)

        if data == "nav:home":
            text, markup = build_start_view(
                first_name=user.first_name,
                bot_username=uname,
                is_private=is_private,
            )
            await _edit_or_reply(query, text, markup)
            await query.answer()

        elif data == "nav:help":
            text, markup = build_help_view(bot_username=uname, show_back=True)
            await _edit_or_reply(query, text, markup)
            await query.answer()

        elif data in ("nav:profile", "profile:refresh"):
            await add_user(user.id, user.username, user.first_name)
            user_doc = await get_user(user.id)
            rank = await get_user_rank(user.id)
            text, markup = build_profile_view(
                user_id=user.id,
                first_name=user.first_name,
                user_doc=user_doc,
                rank=rank,
                show_back=True,
            )
            await _edit_or_reply(query, text, markup)
            await query.answer("🔄 Profile updated!" if data == "profile:refresh" else "")

        elif data == "nav:lb":
            top_users = await get_top_users(10)
            text, markup = build_leaderboard_view(
                mode="users",
                entries=top_users,
                show_back=True,
            )
            await _edit_or_reply(query, text, markup)
            await query.answer()
