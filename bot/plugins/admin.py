from pyrogram import Client, filters
from pyrogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery
from bot.config import SUDO_USERS
from bot.database import db
import asyncio

@Client.on_message(filters.command(["panel", "admin"]) & filters.user(SUDO_USERS))
async def admin_panel(client: Client, message: Message):
    text = "**🛠 Admin Control Panel**\n\nWelcome to the Word Grid Game Admin Dashboard."
    markup = InlineKeyboardMarkup([
        [InlineKeyboardButton("📊 Bot Stats", callback_data="admin_stats")],
        [InlineKeyboardButton("📢 Broadcast", callback_data="admin_broadcast")]
    ])
    await message.reply_text(text, reply_markup=markup)

@Client.on_callback_query(filters.regex("^admin_") & filters.user(SUDO_USERS))
async def admin_callbacks(client: Client, query: CallbackQuery):
    data = query.data

    if data == "admin_stats":
        total_users = await db.get_total_users()
        total_groups = await db.get_total_groups()
        
        text = (
            "**📊 Bot Statistics**\n\n"
            f"👤 Total Users: `{total_users}`\n"
            f"👥 Total Groups: `{total_groups}`"
        )
        markup = InlineKeyboardMarkup([
            [InlineKeyboardButton("⬅️ Back", callback_data="admin_home")]
        ])
        await query.message.edit_text(text, reply_markup=markup)

    elif data == "admin_home":
        text = "**🛠 Admin Control Panel**\n\nWelcome to the Word Grid Game Admin Dashboard."
        markup = InlineKeyboardMarkup([
            [InlineKeyboardButton("📊 Bot Stats", callback_data="admin_stats")],
            [InlineKeyboardButton("📢 Broadcast", callback_data="admin_broadcast")]
        ])
        await query.message.edit_text(text, reply_markup=markup)

    elif data == "admin_broadcast":
        text = (
            "**📢 Broadcast Mode**\n\n"
            "To send a broadcast, reply to any message with the command:\n"
            "`/broadcast`"
        )
        markup = InlineKeyboardMarkup([
            [InlineKeyboardButton("⬅️ Back", callback_data="admin_home")]
        ])
        await query.message.edit_text(text, reply_markup=markup)

@Client.on_message(filters.command("broadcast") & filters.user(SUDO_USERS) & filters.reply)
async def broadcast_command(client: Client, message: Message):
    msg_to_broadcast = message.reply_to_message
    
    users = await db.get_all_users()
    groups = await db.get_all_groups()

    await message.reply_text(f"Starting broadcast to {len(users)} users and {len(groups)} groups...")
    
    success = 0
    failed = 0
    
    # Broadcast to Users
    for user in users:
        try:
            await msg_to_broadcast.copy(user['user_id'])
            success += 1
            await asyncio.sleep(0.1) # Flood wait protection
        except Exception:
            failed += 1

    # Broadcast to Groups
    for group in groups:
        try:
            await msg_to_broadcast.copy(group['chat_id'])
            success += 1
            await asyncio.sleep(0.1)
        except Exception:
            failed += 1

    await message.reply_text(f"✅ **Broadcast Completed!**\n\n🎯 Success: {success}\n❌ Failed: {failed}")
