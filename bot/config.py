import os
from dotenv import load_dotenv

load_dotenv()

API_ID = int(os.getenv("API_ID", "30186171"))
API_HASH = os.getenv("API_HASH", "f4182ae1b16689fa586917e616d8332f")
BOT_TOKEN = os.getenv("BOT_TOKEN", "9283341057:AAH4CPps2ydQI8M8Rs9ylBPlHuUCB9GY6Ns")
MONGO_URI = os.getenv(
    "MONGO_URI",
    "mongodb+srv://iamnobita1:nobitamusic1@cluster0.k08op.mongodb.net/?retryWrites=true&w=majority&appName=Cluster0",
)
DB_NAME = os.getenv("DB_NAME", "WordGridBotDB")
SUDO_USERS = [
    int(x.strip())
    for x in os.getenv("SUDO_USERS", "9267131580, 9267131580").split(",")
    if x.strip().isdigit()
]
BOT_USERNAMES = [
    x.strip().lstrip("@")
    for x in os.getenv("BOT_USERNAMES", os.getenv("BOT_USERNAME", "")).split(",")
    if x.strip().lstrip("@")
]
SUPPORT_GROUP = os.getenv("SUPPORT_GROUP", "https://t.me/cheatbotbase")
UPDATE_CHANNEL = os.getenv("UPDATE_CHANNEL", "https://t.me/aoinetwork")
TIME_ZONE = os.getenv("TIME_ZONE", "Asia/Kolkata")

# Cooldown & Rate-Limit Settings (Seconds)
CMD_COOLDOWN = float(os.getenv("CMD_COOLDOWN", "2.0"))
GAME_START_COOLDOWN = float(os.getenv("GAME_START_COOLDOWN", "2.5"))
HINT_COOLDOWN = float(os.getenv("HINT_COOLDOWN", "10.0"))
REFRESH_COOLDOWN = float(os.getenv("REFRESH_COOLDOWN", "12.0"))
CALLBACK_COOLDOWN = float(os.getenv("CALLBACK_COOLDOWN", "1.0"))
GUESS_COOLDOWN = float(os.getenv("GUESS_COOLDOWN", "0.35"))
MAX_HINTS_PER_ROUND = int(os.getenv("MAX_HINTS_PER_ROUND", "3"))
WORDSEEK_MAX_GUESSES = int(os.getenv("WORDSEEK_MAX_GUESSES", "30"))
PORT = int(os.getenv("PORT", "0"))
