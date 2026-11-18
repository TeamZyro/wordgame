import asyncio
import logging
import time
from pyrogram.errors import FloodWait, MessageNotModified, MessageIdInvalid

logger = logging.getLogger("WordGridBot.Cooldown")

_cooldown_buckets: dict[str, float] = {}
_chat_locks: dict[int, asyncio.Lock] = {}
_user_locks: dict[int, asyncio.Lock] = {}


def check_cooldown(key: str, cooldown_sec: float) -> tuple[bool, float]:
    """
    Checks if `key` is currently on cooldown.
    Returns `(is_allowed, seconds_remaining)`.
    If allowed, records the current monotonic timestamp.
    """
    now = time.monotonic()
    # Periodic bounded cleanup so memory never grows unbounded on Heroku
    if len(_cooldown_buckets) > 2000:
        cutoff = now - 120.0
        expired = [k for k, ts in _cooldown_buckets.items() if ts < cutoff]
        for k in expired:
            _cooldown_buckets.pop(k, None)

    expires_at = _cooldown_buckets.get(key, 0.0)
    if now < expires_at:
        return False, round(expires_at - now, 1)

    _cooldown_buckets[key] = now + cooldown_sec
    return True, 0.0


def reset_cooldown(key: str) -> None:
    _cooldown_buckets.pop(key, None)


def get_chat_lock(chat_id: int) -> asyncio.Lock:
    """Returns a per-chat asyncio.Lock to serialize game state mutations."""
    if len(_chat_locks) > 500:
        unlocked = [cid for cid, lk in _chat_locks.items() if not lk.locked()]
        for cid in unlocked[:250]:
            _chat_locks.pop(cid, None)
    lock = _chat_locks.get(chat_id)
    if lock is None:
        lock = asyncio.Lock()
        _chat_locks[chat_id] = lock
    return lock


def get_user_lock(user_id: int) -> asyncio.Lock:
    """Returns a per-user asyncio.Lock to prevent double-click callback races."""
    if len(_user_locks) > 1000:
        unlocked = [uid for uid, lk in _user_locks.items() if not lk.locked()]
        for uid in unlocked[:500]:
            _user_locks.pop(uid, None)
    lock = _user_locks.get(user_id)
    if lock is None:
        lock = asyncio.Lock()
        _user_locks[user_id] = lock
    return lock


async def safe_tg_call(coro_func, *args, max_wait: int = 15, **kwargs):
    """
    Executes a Pyrogram API coroutine safely with automatic FloodWait handling
    and silent ignoring of benign MessageNotModified errors.
    """
    for attempt in range(2):
        try:
            return await coro_func(*args, **kwargs)
        except MessageNotModified:
            return None
        except MessageIdInvalid:
            return None
        except FloodWait as e:
            wait_sec = int(getattr(e, "value", getattr(e, "x", 5)))
            logger.warning("FloodWait encountered (%ss) on %s", wait_sec, getattr(coro_func, "__name__", "call"))
            if wait_sec <= max_wait and attempt == 0:
                await asyncio.sleep(wait_sec + 0.5)
                continue
            return None
        except Exception as e:
            logger.debug("Telegram API call warning (%s): %s", getattr(coro_func, "__name__", "call"), e)
            return None
    return None
