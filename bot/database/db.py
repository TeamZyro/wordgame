import time
import logging
import random
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo
from motor.motor_asyncio import AsyncIOMotorClient
from bot.config import MONGO_URI, DB_NAME, TIME_ZONE

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

# Word Grid collections (preserved 100% backward-compatible)
users_collection = db["users"]
groups_collection = db["groups"]

# WordSeek collections
seek_scores_collection = db["seek_leaderboard"]
seek_stats_collection = db["seek_user_stats"]
seek_daily_words_collection = db["seek_daily_words"]
seek_daily_guesses_collection = db["seek_daily_guesses"]
seek_auth_collection = db["seek_authorized_users"]
seek_topics_collection = db["seek_chat_topics"]
banned_users_collection = db["banned_users"]

# Lightweight in-memory TTL cache
_CACHE: dict[str, tuple[float, object]] = {}
CACHE_TTL = 15.0  # seconds
_BANNED_CACHE: set[int] = set()
_BANNED_LOADED = False


def _get_cached(key: str):
    entry = _CACHE.get(key)
    if entry and (time.monotonic() - entry[0]) < CACHE_TTL:
        return entry[1]
    return None


def _set_cached(key: str, value):
    if len(_CACHE) > 256:
        _CACHE.clear()
    _CACHE[key] = (time.monotonic(), value)


def invalidate_leaderboard_cache():
    for k in list(_CACHE.keys()):
        if k.startswith(("top_", "total_", "seek_lb_", "seek_score_")):
            _CACHE.pop(k, None)


async def init_db():
    """Ensure indexes exist for both Word Grid and WordSeek collections."""
    try:
        await users_collection.create_index("user_id", unique=True, background=True)
        await users_collection.create_index([("score", -1)], background=True)
        await groups_collection.create_index("chat_id", unique=True, background=True)
        await groups_collection.create_index([("score", -1)], background=True)

        # WordSeek indexes
        await seek_scores_collection.create_index(
            [("word_length", 1), ("chat_id", 1), ("created_at", -1)],
            background=True,
        )
        await seek_scores_collection.create_index(
            [("user_id", 1), ("word_length", 1), ("created_at", -1)],
            background=True,
        )
        await seek_stats_collection.create_index("user_id", unique=True, background=True)
        await seek_daily_words_collection.create_index("date", unique=True, background=True)
        await seek_daily_guesses_collection.create_index(
            [("user_id", 1), ("date", 1), ("attempt_number", 1)],
            background=True,
        )
        await seek_auth_collection.create_index(
            [("chat_id", 1), ("user_id", 1)], unique=True, background=True
        )
        await seek_topics_collection.create_index(
            [("chat_id", 1), ("topic_id", 1)], unique=True, background=True
        )
        await banned_users_collection.create_index("user_id", unique=True, background=True)
        logger.info("MongoDB connected and all indexes verified on '%s'.", DB_NAME)
    except Exception as e:
        logger.warning("MongoDB index initialization warning: %s", e)


async def close_db():
    try:
        client.close()
    except Exception as e:
        logger.warning("Error closing MongoDB client: %s", e)


# ============================================================================
# BANNED USERS MANAGEMENT
# ============================================================================
async def is_user_banned(user_id: int) -> bool:
    global _BANNED_LOADED
    if not _BANNED_LOADED:
        try:
            cursor = banned_users_collection.find({}, {"user_id": 1})
            docs = await cursor.to_list(length=None)
            _BANNED_CACHE.clear()
            for d in docs:
                if "user_id" in d:
                    _BANNED_CACHE.add(int(d["user_id"]))
            _BANNED_LOADED = True
        except Exception:
            pass
    return user_id in _BANNED_CACHE


async def ban_user(user_id: int) -> bool:
    try:
        _BANNED_CACHE.add(int(user_id))
        await banned_users_collection.update_one(
            {"user_id": int(user_id)},
            {"$set": {"user_id": int(user_id), "created_at": datetime.now(timezone.utc)}},
            upsert=True,
        )
        invalidate_leaderboard_cache()
        return True
    except Exception as e:
        logger.error("Failed to ban user %s: %s", user_id, e)
        return False


async def unban_user(user_id: int) -> bool:
    try:
        _BANNED_CACHE.discard(int(user_id))
        res = await banned_users_collection.delete_one({"user_id": int(user_id)})
        invalidate_leaderboard_cache()
        return res.deleted_count > 0
    except Exception as e:
        logger.error("Failed to unban user %s: %s", user_id, e)
        return False


# ============================================================================
# WORD GRID ARCADE DB OPERATIONS
# ============================================================================
async def add_user(user_id: int, username: str | None, first_name: str):
    try:
        await users_collection.update_one(
            {"user_id": user_id},
            {
                "$set": {
                    "username": (username or "").lower(),
                    "display_username": username or "",
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
            set_fields["username"] = username.lower()
            set_fields["display_username"] = username
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


async def find_user_by_username_or_id(identifier: str) -> dict | None:
    ident = identifier.strip().lstrip("@")
    try:
        if ident.lstrip("-").isdigit():
            return await users_collection.find_one({"user_id": int(ident)})
        return await users_collection.find_one({"username": ident.lower()})
    except Exception:
        return None


async def get_user_rank(user_id: int) -> int:
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


# ============================================================================
# WORDSEEK LEADERBOARD, SCORES & DAILY STATS
# ============================================================================
def _get_time_cutoff(time_key: str) -> datetime | None:
    now = datetime.now(timezone.utc)
    if time_key == "today":
        return now.replace(hour=0, minute=0, second=0, microsecond=0)
    if time_key == "week":
        start_of_day = now.replace(hour=0, minute=0, second=0, microsecond=0)
        return start_of_day - timedelta(days=now.weekday())
    if time_key == "month":
        return now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    if time_key == "year":
        return now.replace(month=1, day=1, hour=0, minute=0, second=0, microsecond=0)
    return None


async def add_seek_score(
    user_id: int,
    first_name: str,
    username: str | None,
    chat_id: int,
    score: int,
    word_length: int = 5,
):
    """Records a WordSeek win in `seek_leaderboard` and updates the user profile."""
    try:
        await add_user(user_id, username, first_name)
        await seek_scores_collection.insert_one(
            {
                "user_id": int(user_id),
                "name": first_name or "Player",
                "username": username or None,
                "chat_id": int(chat_id),
                "score": int(score),
                "word_length": int(word_length),
                "created_at": datetime.now(timezone.utc),
            }
        )
        await users_collection.update_one(
            {"user_id": int(user_id)},
            {"$inc": {"seek_score": int(score), "seek_wins": 1}},
        )
        invalidate_leaderboard_cache()
    except Exception as e:
        logger.error("Failed to record WordSeek score for %s: %s", user_id, e)


async def get_seek_leaderboard(
    chat_id: int,
    search_key: str = "group",
    time_key: str = "all",
    word_length: int = 5,
    limit: int = 15,
    force_refresh: bool = False,
) -> list[dict]:
    cache_key = f"seek_lb_{chat_id}_{search_key}_{time_key}_{word_length}"
    if not force_refresh:
        cached = _get_cached(cache_key)
        if cached is not None:
            return cached

    match_stage: dict = {"word_length": int(word_length)}
    if search_key == "group":
        match_stage["chat_id"] = int(chat_id)
    if _BANNED_CACHE:
        match_stage["user_id"] = {"$nin": list(_BANNED_CACHE)}

    cutoff = _get_time_cutoff(time_key)
    if cutoff is not None:
        match_stage["created_at"] = {"$gte": cutoff}

    pipeline = [
        {"$match": match_stage},
        {
            "$group": {
                "_id": "$user_id",
                "user_id": {"$first": "$user_id"},
                "name": {"$last": "$name"},
                "username": {"$last": "$username"},
                "total_score": {"$sum": "$score"},
                "wins": {"$sum": 1},
            }
        },
        {"$sort": {"total_score": -1}},
        {"$limit": limit},
    ]
    try:
        cursor = seek_scores_collection.aggregate(pipeline)
        res = await cursor.to_list(length=limit)
        _set_cached(cache_key, res)
        return res
    except Exception as e:
        logger.error("Failed to aggregate WordSeek leaderboard: %s", e)
        return []


async def get_seek_user_score(
    user_id: int,
    chat_id: int,
    search_key: str = "global",
    time_key: str = "all",
    word_length: int = 5,
) -> dict | None:
    match_stage: dict = {"word_length": int(word_length)}
    if search_key == "group":
        match_stage["chat_id"] = int(chat_id)
    if _BANNED_CACHE:
        match_stage["user_id"] = {"$nin": list(_BANNED_CACHE)}

    cutoff = _get_time_cutoff(time_key)
    if cutoff is not None:
        match_stage["created_at"] = {"$gte": cutoff}

    pipeline = [
        {"$match": match_stage},
        {
            "$group": {
                "_id": "$user_id",
                "user_id": {"$first": "$user_id"},
                "name": {"$last": "$name"},
                "username": {"$last": "$username"},
                "total_score": {"$sum": "$score"},
                "wins": {"$sum": 1},
            }
        },
        {"$sort": {"total_score": -1}},
    ]
    try:
        cursor = seek_scores_collection.aggregate(pipeline)
        all_rows = await cursor.to_list(length=None)
        target_row = None
        rank = 0
        for idx, row in enumerate(all_rows):
            if int(row["user_id"]) == int(user_id):
                target_row = row
                rank = idx + 1
                break

        stats_doc = await seek_stats_collection.find_one({"user_id": int(user_id)})
        user_doc = await get_user(int(user_id))

        if not target_row and not stats_doc:
            return None

        return {
            "user_id": int(user_id),
            "name": (target_row or {}).get("name") or (user_doc or {}).get("first_name", "Player"),
            "username": (target_row or {}).get("username") or (user_doc or {}).get("display_username"),
            "total_score": (target_row or {}).get("total_score", 0),
            "wins": (target_row or {}).get("wins", 0),
            "rank": rank,
            "current_streak": (stats_doc or {}).get("current_streak", 0),
            "highest_streak": (stats_doc or {}).get("highest_streak", 0),
        }
    except Exception as e:
        logger.error("Failed to fetch WordSeek user score for %s: %s", user_id, e)
        return None


async def transfer_seek_scores(from_user_id: int, to_user_id: int) -> int:
    try:
        to_doc = await get_user(to_user_id)
        update_fields: dict = {"user_id": int(to_user_id)}
        if to_doc:
            update_fields["name"] = to_doc.get("first_name", "Player")
            update_fields["username"] = to_doc.get("display_username")
        res = await seek_scores_collection.update_many(
            {"user_id": int(from_user_id)},
            {"$set": update_fields},
        )
        invalidate_leaderboard_cache()
        return res.modified_count
    except Exception as e:
        logger.error("Failed to transfer scores: %s", e)
        return 0


# ============================================================================
# DAILY WORDSEEK (WORD OF THE DAY & STREAKS)
# ============================================================================
def get_current_game_date_string() -> str:
    """Returns YYYY-MM-DD in configured TIME_ZONE, rolling over at 06:00 AM."""
    try:
        tz = ZoneInfo(TIME_ZONE)
    except Exception:
        tz = timezone.utc
    now = datetime.now(tz)
    if now.hour < 6:
        now = now - timedelta(days=1)
    return now.strftime("%Y-%m-%d")


async def get_or_create_daily_word(
    date_str: str,
    daily_pool: list[str],
    common_words_dict: dict,
) -> dict:
    try:
        existing = await seek_daily_words_collection.find_one({"date": date_str})
        if existing:
            return existing

        count = await seek_daily_words_collection.count_documents({})
        day_number = count + 1

        # Deterministic or random pick from daily_pool
        word = random.choice(daily_pool).lower() if daily_pool else "flame"
        details = common_words_dict.get(word, {})
        doc = {
            "date": date_str,
            "day_number": day_number,
            "word": word,
            "meaning": details.get("meaning"),
            "phonetic": details.get("pronunciation"),
            "sentence": details.get("example"),
            "created_at": datetime.now(timezone.utc),
        }
        await seek_daily_words_collection.insert_one(doc)
        return doc
    except Exception as e:
        logger.error("Error getting/creating daily word: %s", e)
        return {
            "date": date_str,
            "day_number": 1,
            "word": "spark",
            "meaning": "A small fiery particle thrown off from a fire.",
            "phonetic": "/spɑːrk/",
            "sentence": "A single spark can start a great fire.",
        }


async def get_daily_guesses(user_id: int, date_str: str) -> list[dict]:
    try:
        cursor = seek_daily_guesses_collection.find(
            {"user_id": int(user_id), "date": date_str}
        ).sort("attempt_number", 1)
        return await cursor.to_list(length=10)
    except Exception:
        return []


async def add_daily_guess(user_id: int, date_str: str, guess: str, attempt_number: int):
    try:
        await seek_daily_guesses_collection.insert_one(
            {
                "user_id": int(user_id),
                "date": date_str,
                "guess": guess.lower(),
                "attempt_number": attempt_number,
                "created_at": datetime.now(timezone.utc),
            }
        )
    except Exception as e:
        logger.error("Failed to insert daily guess: %s", e)


async def update_daily_streak(user_id: int, won: bool, date_str: str) -> tuple[int, int]:
    """Updates user's daily streak and returns `(current_streak, highest_streak)`."""
    try:
        stats = await seek_stats_collection.find_one({"user_id": int(user_id)})
        curr = (stats or {}).get("current_streak", 0)
        high = (stats or {}).get("highest_streak", 0)
        last_date = (stats or {}).get("last_date")

        if not won:
            new_curr = 0
            new_high = high
        else:
            if last_date == date_str:
                new_curr = max(1, curr)
            else:
                try:
                    d_today = datetime.strptime(date_str, "%Y-%m-%d").date()
                    d_last = datetime.strptime(last_date, "%Y-%m-%d").date() if last_date else None
                    if d_last and (d_today - d_last).days == 1:
                        new_curr = curr + 1
                    else:
                        new_curr = 1
                except Exception:
                    new_curr = 1
            new_high = max(high, new_curr)

        await seek_stats_collection.update_one(
            {"user_id": int(user_id)},
            {
                "$set": {
                    "current_streak": new_curr,
                    "highest_streak": new_high,
                    "last_date": date_str,
                    "updated_at": datetime.now(timezone.utc),
                }
            },
            upsert=True,
        )
        return new_curr, new_high
    except Exception as e:
        logger.error("Failed to update daily streak: %s", e)
        return (1 if won else 0), (1 if won else 0)


# ============================================================================
# GROUP AUTHORIZATION (/seekauth) & FORUM TOPICS (/setgametopic, /allowonlylen)
# ============================================================================
async def is_seek_authorized(chat_id: int, user_id: int) -> bool:
    try:
        doc = await seek_auth_collection.find_one(
            {"chat_id": int(chat_id), "user_id": int(user_id)}
        )
        return doc is not None
    except Exception:
        return False


async def authorize_seek_user(
    chat_id: int, user_id: int, name: str, username: str | None, authorized_by: int
) -> bool:
    try:
        await seek_auth_collection.update_one(
            {"chat_id": int(chat_id), "user_id": int(user_id)},
            {
                "$set": {
                    "name": name,
                    "username": username,
                    "authorized_by": int(authorized_by),
                    "created_at": datetime.now(timezone.utc),
                }
            },
            upsert=True,
        )
        return True
    except Exception:
        return False


async def remove_seek_user(chat_id: int, user_id: int) -> bool:
    try:
        res = await seek_auth_collection.delete_one(
            {"chat_id": int(chat_id), "user_id": int(user_id)}
        )
        return res.deleted_count > 0
    except Exception:
        return False


async def list_seek_users(chat_id: int) -> list[dict]:
    try:
        cursor = seek_auth_collection.find({"chat_id": int(chat_id)})
        return await cursor.to_list(length=50)
    except Exception:
        return []


async def set_game_topic(chat_id: int, topic_id: str) -> bool:
    try:
        existing = await seek_topics_collection.find_one(
            {"chat_id": int(chat_id), "topic_id": str(topic_id)}
        )
        if existing:
            return False
        await seek_topics_collection.insert_one(
            {
                "chat_id": int(chat_id),
                "topic_id": str(topic_id),
                "allowed_lengths": [5, 4, 6],
                "created_at": datetime.now(timezone.utc),
            }
        )
        return True
    except Exception:
        return False


async def unset_game_topic(chat_id: int, topic_id: str) -> bool:
    try:
        res = await seek_topics_collection.delete_one(
            {"chat_id": int(chat_id), "topic_id": str(topic_id)}
        )
        return res.deleted_count > 0
    except Exception:
        return False


async def get_game_topics(chat_id: int) -> list[dict]:
    try:
        cursor = seek_topics_collection.find({"chat_id": int(chat_id)})
        return await cursor.to_list(length=20)
    except Exception:
        return []


async def set_topic_allowed_lengths(chat_id: int, topic_id: str, lengths: list[int]) -> bool:
    try:
        res = await seek_topics_collection.update_one(
            {"chat_id": int(chat_id), "topic_id": str(topic_id)},
            {"$set": {"allowed_lengths": lengths}},
        )
        return res.matched_count > 0
    except Exception:
        return False
