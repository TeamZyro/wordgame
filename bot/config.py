import os
from dotenv import load_dotenv

load_dotenv()

API_ID = os.getenv("API_ID", "30186171")
API_HASH = os.getenv("API_HASH", "f4182ae1b16689fa586917e616d8332f")
BOT_TOKEN = os.getenv("BOT_TOKEN", "8519924243:AAGwus55Q9rHdb8npYkshJDwnj2PkL_bxu4")
MONGO_URI = os.getenv("MONGO_URI", "mongodb+srv://iamnobita1:nobitamusic1@cluster0.k08op.mongodb.net/?retryWrites=true&w=majority&appName=Cluster0")
DB_NAME = os.getenv("DB_NAME", "WordGridBotDB")
SUDO_USERS = [int(x) for x in os.getenv("SUDO_USERS", "1106006604, 7638720582").split(",") if x.strip()]
SUPPORT_GROUP = os.getenv("SUPPORT_GROUP", "https://t.me/+S0Q1-J_EQLA3YmU1")
UPDATE_CHANNEL = os.getenv("UPDATE_CHANNEL", "https://t.me/NOBITA_SUPP0RT")
