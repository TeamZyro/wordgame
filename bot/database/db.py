import time
import logging
from motor.motor_asyncio import AsyncIOMotorClient
from bot.config import MONGO_URI, DB_NAME

logger = logging.getLogger("WordGridBot.DB")

# Heroku-optimized Motor client with bounded pool size for 512MB RAM dynos
client = AsyncIOMotorClient(
    MONGO_URI,
    maxPoolSize=20,
    minPoolSize=1,
    serverSelectionTimeoutMS=5000,
    connectTimeoutMS=5000,
    retryWrites=True,
)
db = client[DB_NAME]
users_collection = db["users"]
groups_collection = db["groups"]

# Lightweight in-memory TTL cache to avoid repeated heavy queries on leaderboard/stats clicks
_CACHE = {}
CACHE_TTL = 15.0  # seconds


def _get_cached(key: str):
    entry = _CACHE.get(key)
    if entry and (time.monotonic() - entry[0]) < CACHE_TTL:
        return entry[1]
    return None


def _set_cached(key: str, value):
    if len(_CACHE) > 128:
        _CACHE.clear()
    _CACHE[key] = (time.monotonic(), value)


def invalidate_leaderboard_cache():
    for k in list(_CACHE.keys()):
        if k.startswith(("top_", "total_")):
            _CACHE.pop(k, None)


async def init_db():
    """Ensure indexes exist for fast queries without altering existing documents."""
    try:
        await users_collection.create_index("user_id", unique=True, background=True)
        await users_collection.create_index([("score", -1)], background=True)
        await groups_collection.create_index("chat_id", unique=True, background=True)
        await groups_collection.create_index([("score", -1)], background=True)
        logger.info("MongoDB connected and indexes verified on database '%s'.", DB_NAME)
    except Exception as e:
        logger.warning("MongoDB index initialization warning: %s", e)


async def close_db():
    try:
        client.close()
    except Exception as e:
        logger.warning("Error closing MongoDB client: %s", e)


async def add_user(user_id: int, username: str | None, first_name: str):
    try:
        await users_collection.update_one(
            {"user_id": user_id},
            {
                "$set": {
                    "username": username or "",
                    "first_name": first_name or "Player",
                },
                "$setOnInsert": {
                    "score": 0,
                    "games_played": 0,
                    "words_found": 0,
                    "best_round": 1,
                },
            },
            upsert=True,
        )
    except Exception as e:
        logger.error("Failed to upsert user %s: %s", user_id, e)


async def add_group(chat_id: int, title: str | None):
    try:
        await groups_collection.update_one(
            {"chat_id": chat_id},
            {
                "$set": {"title": title or "Group Chat"},
                "$setOnInsert": {
                    "score": 0,
                    "games_played": 0,
                    "best_round": 1,
                },
            },
            upsert=True,
        )
    except Exception as e:
        logger.error("Failed to upsert group %s: %s", chat_id, e)


async def add_score(
    user_id: int,
    first_name: str,
    points: int,
    round_num: int = 1,
    username: str | None = None,
):
    try:
        set_fields = {"first_name": first_name or "Player"}
        if username:
            set_fields["username"] = username
        await users_collection.update_one(
            {"user_id": user_id},
            {
                "$inc": {"score": points, "games_played": 1, "words_found": 1},
                "$set": set_fields,
                "$max": {"best_round": round_num},
            },
            upsert=True,
        )
        invalidate_leaderboard_cache()
    except Exception as e:
        logger.error("Failed to add score for user %s: %s", user_id, e)


async def add_group_score(chat_id: int, title: str | None, points: int, round_num: int = 1):
    try:
        await groups_collection.update_one(
            {"chat_id": chat_id},
            {
                "$inc": {"score": points, "games_played": 1},
                "$set": {"title": title or "Group Chat"},
                "$max": {"best_round": round_num},
            },
            upsert=True,
        )
        invalidate_leaderboard_cache()
    except Exception as e:
        logger.error("Failed to add score for group %s: %s", chat_id, e)


async def get_user(user_id: int) -> dict | None:
    try:
        return await users_collection.find_one({"user_id": user_id})
    except Exception as e:
        logger.error("Failed to get user %s: %s", user_id, e)
        return None


async def get_user_rank(user_id: int) -> int:
    """Returns 1-based global rank of the user by score (0 if unranked)."""
    try:
        user_doc = await get_user(user_id)
        if not user_doc or user_doc.get("score", 0) <= 0:
            return 0
        higher_count = await users_collection.count_documents(
            {"score": {"$gt": user_doc.get("score", 0)}}
        )
        return higher_count + 1
    except Exception as e:
        logger.error("Failed to compute rank for user %s: %s", user_id, e)
        return 0


async def get_top_users(limit: int = 10, force_refresh: bool = False) -> list[dict]:
    cache_key = f"top_users_{limit}"
    if not force_refresh:
        cached = _get_cached(cache_key)
        if cached is not None:
            return cached
    try:
        cursor = users_collection.find({"score": {"$gt": 0}}).sort("score", -1).limit(limit)
        res = await cursor.to_list(length=limit)
        if not res:
            cursor = users_collection.find().sort("score", -1).limit(limit)
            res = await cursor.to_list(length=limit)
        _set_cached(cache_key, res)
        return res
    except Exception as e:
        logger.error("Failed to fetch top users: %s", e)
        return []


async def get_top_groups(limit: int = 10, force_refresh: bool = False) -> list[dict]:
    cache_key = f"top_groups_{limit}"
    if not force_refresh:
        cached = _get_cached(cache_key)
        if cached is not None:
            return cached
    try:
        cursor = groups_collection.find({"score": {"$gt": 0}}).sort("score", -1).limit(limit)
        res = await cursor.to_list(length=limit)
        if not res:
            cursor = groups_collection.find().sort("score", -1).limit(limit)
            res = await cursor.to_list(length=limit)
        _set_cached(cache_key, res)
        return res
    except Exception as e:
        logger.error("Failed to fetch top groups: %s", e)
        return []


async def get_total_users(force_refresh: bool = False) -> int:
    if not force_refresh:
        cached = _get_cached("total_users")
        if cached is not None:
            return cached
    try:
        count = await users_collection.count_documents({})
        _set_cached("total_users", count)
        return count
    except Exception as e:
        logger.error("Failed to count users: %s", e)
        return 0


async def get_total_groups(force_refresh: bool = False) -> int:
    if not force_refresh:
        cached = _get_cached("total_groups")
        if cached is not None:
            return cached
    try:
        count = await groups_collection.count_documents({})
        _set_cached("total_groups", count)
        return count
    except Exception as e:
        logger.error("Failed to count groups: %s", e)
        return 0


async def get_all_users() -> list[dict]:
    try:
        cursor = users_collection.find({}, {"user_id": 1})
        return await cursor.to_list(length=None)
    except Exception as e:
        logger.error("Failed to list all users: %s", e)
        return []


async def get_all_groups() -> list[dict]:
    try:
        cursor = groups_collection.find({}, {"chat_id": 1})
        return await cursor.to_list(length=None)
    except Exception as e:
        logger.error("Failed to list all groups: %s", e)
        return []
