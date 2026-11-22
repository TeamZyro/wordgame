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
    get_seek_user_score,
    get_seek_leaderboard,
    is_user_banned,
)
from bot.config import CMD_COOLDOWN, CALLBACK_COOLDOWN, SUDO_USERS
from bot.utils.cooldown import check_cooldown, get_user_lock, safe_tg_call
from bot.utils.command_filter import bot_command, get_primary_bot_username
from bot.utils.rich_api import (
    send_rich_message,
    edit_rich_message,
    edit_styled_message,
)
from bot.utils.views import (
    build_start_view,
    build_help_view,
    build_rich_help_html,
    build_help_keyboard_dict,
    build_profile_view,
    build_seek_leaderboard_view,
)

logger = logging.getLogger("WordGridBot.Start")

START_IMG_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), "utils", "start_img.png")
_CACHED_START_FILE_ID: str | None = None


async def _send_start_media_or_text(client: Client, message: Message, text: str, markup):
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


async def edit_or_reply_view(query: CallbackQuery, text: str, markup):
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


@Client.on_message(bot_command(["start"]))
async def start_command(client: Client, message: Message):
    user = message.from_user
    if user:
        if await is_user_banned(user.id):
            return
        allowed, _ = check_cooldown(f"cmd:start:{user.id}", CMD_COOLDOWN)
        if not allowed:
            return

    uname = get_primary_bot_username(client, fallback="WordGridGameBot")

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


@Client.on_message(bot_command(["help"]))
async def help_command(client: Client, message: Message):
    user = message.from_user
    if user:
        if await is_user_banned(user.id):
            return
        allowed, _ = check_cooldown(f"cmd:help:{user.id}", CMD_COOLDOWN)
        if not allowed:
            return

    uname = get_primary_bot_username(client, fallback="WordGridGameBot")
    is_admin = bool(user and user.id in SUDO_USERS and message.chat.type == ChatType.PRIVATE)

    rich_html = build_rich_help_html("howto")
    kb_dict = build_help_keyboard_dict(is_admin=is_admin, active="howto", show_back=False)

    sent = await send_rich_message(
        chat_id=message.chat.id,
        html_content=rich_html,
        reply_markup=kb_dict,
        message_thread_id=getattr(message, "message_thread_id", None),
    )
    if not sent:
        text, markup = build_help_view(
            bot_username=uname,
            section="howto",
            is_admin=is_admin,
            show_back=False,
        )
        await safe_tg_call(message.reply_text, text, reply_markup=markup)


@Client.on_message(bot_command(["profile", "rank", "me"]))
async def profile_command(client: Client, message: Message):
    user = message.from_user
    if not user or await is_user_banned(user.id):
        return
    allowed, _ = check_cooldown(f"cmd:profile:{user.id}", CMD_COOLDOWN)
    if not allowed:
        return

    await add_user(user.id, user.username, user.first_name)
    user_doc = await get_user(user.id)
    rank = await get_user_rank(user.id)
    seek_data = await get_seek_user_score(user.id, message.chat.id, "global", "all", 5)
    text, markup = build_profile_view(
        user_id=user.id,
        first_name=user.first_name,
        user_doc=user_doc,
        rank=rank,
        seek_data=seek_data,
        show_back=(message.chat.type == ChatType.PRIVATE),
    )
    await safe_tg_call(message.reply_text, text, reply_markup=markup)


@Client.on_callback_query(filters.regex(r"^(nav:|profile:|help[:_])"))
async def navigation_callbacks(client: Client, query: CallbackQuery):
    user = query.from_user
    if not user or await is_user_banned(user.id):
        await query.answer()
        return

    allowed, wait_sec = check_cooldown(f"cb:nav:{user.id}", CALLBACK_COOLDOWN)
    if not allowed:
        await query.answer(f"⏳ Wait {wait_sec}s!", show_alert=False)
        return

    async with get_user_lock(user.id):
        data = query.data.replace("help_", "help:")
        uname = get_primary_bot_username(client, fallback="WordGridGameBot")
        is_private = bool(query.message and query.message.chat.type == ChatType.PRIVATE)
        is_admin = bool(user.id in SUDO_USERS and is_private)

        if data == "nav:home":
            text, markup = build_start_view(
                first_name=user.first_name,
                bot_username=uname,
                is_private=is_private,
            )
            await edit_or_reply_view(query, text, markup)
            await query.answer()

        elif data == "nav:help" or data.startswith("help:"):
            sec = data.split(":", 1)[1] if ":" in data and data != "nav:help" else "howto"
            if sec == "main":
                sec = "howto"
            if sec == "admin" and not is_admin:
                await query.answer("You don't have permission to view this.", show_alert=True)
                return

            if query.message and query.message.photo:
                text, markup = build_help_view(
                    bot_username=uname,
                    section=sec,
                    is_admin=is_admin,
                    show_back=True,
                )
                await edit_or_reply_view(query, text, markup)
            elif query.message:
                rich_html = build_rich_help_html(sec)
                kb_dict = build_help_keyboard_dict(is_admin=is_admin, active=sec, show_back=False)
                edited = await edit_rich_message(
                    chat_id=query.message.chat.id,
                    message_id=query.message.id,
                    html_content=rich_html,
                    reply_markup=kb_dict,
                )
                if not edited:
                    text, markup = build_help_view(
                        bot_username=uname,
                        section=sec,
                        is_admin=is_admin,
                        show_back=False,
                    )
                    await edit_or_reply_view(query, text, markup)
            await query.answer()

        elif data in ("nav:profile", "profile:refresh"):
            await add_user(user.id, user.username, user.first_name)
            user_doc = await get_user(user.id)
            rank = await get_user_rank(user.id)
            chat_id = query.message.chat.id if query.message else user.id
            seek_data = await get_seek_user_score(user.id, chat_id, "global", "all", 5)
            text, markup = build_profile_view(
                user_id=user.id,
                first_name=user.first_name,
                user_doc=user_doc,
                rank=rank,
                seek_data=seek_data,
                show_back=True,
            )
            await edit_or_reply_view(query, text, markup)
            await query.answer("🔄 Updated!" if data == "profile:refresh" else "")

        elif data == "nav:lb":
            chat_id = query.message.chat.id if query.message else user.id
            entries = await get_seek_leaderboard(chat_id, "global", "all", 5)
            text, pyro_markup, styled_kb_dict = build_seek_leaderboard_view(
                entries=entries,
                search_key="global",
                time_key="all",
                word_length=5,
                show_back=True,
            )
            if query.message and not query.message.photo:
                edited = await edit_styled_message(
                    chat_id=chat_id,
                    message_id=query.message.id,
                    text_html=text,
                    reply_markup=styled_kb_dict,
                )
                if not edited:
                    await edit_or_reply_view(query, text, pyro_markup)
            else:
                await edit_or_reply_view(query, text, pyro_markup)
            await query.answer()
