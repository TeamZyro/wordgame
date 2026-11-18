import os
from dotenv import load_dotenv

load_dotenv()

API_ID = int(os.getenv("API_ID", "30186171"))
API_HASH = os.getenv("API_HASH", "f4182ae1b16689fa586917e616d8332f")
BOT_TOKEN = os.getenv("BOT_TOKEN", "8682240083:AAE9ZrYe4rixE1_yrLTI3CoO-pwUw9l0dmg")
MONGO_URI = os.getenv(
    "MONGO_URI",
    "mongodb+srv://iamnobita1:nobitamusic1@cluster0.k08op.mongodb.net/?retryWrites=true&w=majority&appName=Cluster0",
)
DB_NAME = os.getenv("DB_NAME", "WordGridBotDB")
SUDO_USERS = [
    int(x.strip())
    for x in os.getenv("SUDO_USERS", "1106006604, 7638720582").split(",")
    if x.strip().isdigit()
]
SUPPORT_GROUP = os.getenv("SUPPORT_GROUP", "https://t.me/+S0Q1-J_EQLA3YmU1")
UPDATE_CHANNEL = os.getenv("UPDATE_CHANNEL", "https://t.me/NOBITA_SUPP0RT")

# Cooldown & Rate-Limit Settings (Seconds)
CMD_COOLDOWN = float(os.getenv("CMD_COOLDOWN", "2.5"))
GAME_START_COOLDOWN = float(os.getenv("GAME_START_COOLDOWN", "3.0"))
HINT_COOLDOWN = float(os.getenv("HINT_COOLDOWN", "10.0"))
REFRESH_COOLDOWN = float(os.getenv("REFRESH_COOLDOWN", "12.0"))
CALLBACK_COOLDOWN = float(os.getenv("CALLBACK_COOLDOWN", "1.2"))
GUESS_COOLDOWN = float(os.getenv("GUESS_COOLDOWN", "0.4"))
MAX_HINTS_PER_ROUND = int(os.getenv("MAX_HINTS_PER_ROUND", "3"))
PORT = int(os.getenv("PORT", "0"))
