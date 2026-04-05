import os
from pyrogram import Client, filters
from pyrogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton
from pyrogram.enums import ChatType
from bot.database.db import add_user, add_group
from bot.config import SUPPORT_GROUP, UPDATE_CHANNEL

START_PIC = os.path.join(os.path.dirname(__file__), "..", "utils", "start_img.png")

@Client.on_message(filters.command(["start"]))
async def start_command(client: Client, message: Message):
    if message.chat.type == ChatType.PRIVATE:
        await add_user(message.from_user.id, message.from_user.username, message.from_user.first_name)
        
        text = (
            f"**Welcome to the Word Grid Arcade!** 🧩\n\n"
            f"Hello {message.from_user.first_name}, I am an interactive 3D Word Search game bot. "
            f"Challenge your friends to infinite arcade rounds dynamically getting harder as you progress!\n\n"
            f"**Commands:**\n"
            f"🎮 `/game` - Start an Arcade Session\n"
            f"🛑 `/stopgame` - End current session\n"
            f"🏆 `/leaderboard` - View Global Ranks\n"
            f"📖 `/help` - How to play"
        )
        
        markup = InlineKeyboardMarkup([
            [InlineKeyboardButton("➕ Add to your Group ➕", url=f"https://t.me/{client.me.username}?startgroup=true")],
            [InlineKeyboardButton("💬 Support GC", url=SUPPORT_GROUP), 
             InlineKeyboardButton("📢 Channel", url=UPDATE_CHANNEL)]
        ])
        
        if os.path.exists(START_PIC):
            await message.reply_photo(photo=START_PIC, caption=text, reply_markup=markup)
        else:
            await message.reply_text(text, reply_markup=markup)
    else:
        await add_group(message.chat.id, message.chat.title)
        text = "Hello! I am ready to host Word Grid Puzzles in this group. Use /game to start an arcade session!"
        await message.reply_text(text)

@Client.on_message(filters.command(["help"]))
async def help_command(client: Client, message: Message):
    text = (
        "**📚 How to Play Arcade Mode:**\n\n"
        "1. Send `/game` in your group to start Round 1.\n"
        "2. Find words hidden horizontally, vertically, or diagonally!\n"
        "3. Hints are provided in the caption like `L _ _ E`.\n"
        "4. Simply type the word you found in the chat to score points.\n"
        "5. Solve the grid before the time limit expires to automatically advance to the next harder round.\n"
        "6. If time expires, you lose your streak and fall back to Round 1."
    )
    markup = InlineKeyboardMarkup([
        [InlineKeyboardButton("💬 Need Help?", url=SUPPORT_GROUP)]
    ])
    
    if message.chat.type == ChatType.PRIVATE and os.path.exists(START_PIC):
        await message.reply_photo(photo=START_PIC, caption=text, reply_markup=markup)
    else:
        await message.reply_text(text, reply_markup=markup)
