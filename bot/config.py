import os
from dotenv import load_dotenv

load_dotenv()

API_ID = os.getenv("API_ID", "21851852")
API_HASH = os.getenv("API_HASH", "3f984666ff0d7b389256896352912a8a")
BOT_TOKEN = os.getenv("BOT_TOKEN", "8519924243:AAGwus55Q9rHdb8npYkshJDwnj2PkL_bxu4")
MONGO_URI = os.getenv("MONGO_URI", "mongodb+srv://harshmanjhi1801:webapp@cluster0.xxwc4.mongodb.net/?")
DB_NAME = os.getenv("DB_NAME", "WordGridBotDB")
SUDO_USERS = [int(x) for x in os.getenv("SUDO_USERS", "7638720582, 7638720582").split(",") if x.strip()]

SUPPORT_GROUP = os.getenv("SUPPORT_GROUP", "https://t.me/ZyroSupport")
UPDATE_CHANNEL = os.getenv("UPDATE_CHANNEL", "https://t.me/ZyroBots")
