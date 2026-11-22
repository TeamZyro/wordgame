import logging
import time
from typing import Iterable
from pyrogram import Client, filters
from pyrogram.types import Message
from bot.config import BOT_USERNAMES
from bot.utils.rich_api import call_bot_api

logger = logging.getLogger("WordGridBot.CommandFilter")

_CACHE_TTL_SECONDS = 600.0


def _extract_usernames_from_user(user_obj) -> tuple[set[str], str | None]:
    """
    Extracts all active usernames (both primary `user.username` and Fragment
    collectible / multiple `user.usernames`) from a Pyrogram/Pyrofork User object.
    Returns `(lowercase_usernames_set, preferred_display_username)`.
    """
    found: set[str] = set()
    primary: str | None = None

    if user_obj is None:
        return found, primary

    raw_primary = getattr(user_obj, "username", None)
    if isinstance(raw_primary, str) and raw_primary.strip():
        clean = raw_primary.strip().lstrip("@")
        primary = clean
        found.add(clean.casefold())

    extra_list = getattr(user_obj, "usernames", None) or []
    for item in extra_list:
        uname = getattr(item, "username", None) if not isinstance(item, str) else item
        is_active = getattr(item, "active", True) if not isinstance(item, str) else True
        if isinstance(uname, str) and uname.strip() and is_active:
            clean = uname.strip().lstrip("@")
            if primary is None:
                primary = clean
            found.add(clean.casefold())

    return found, primary


async def refresh_bot_usernames(client: Client, me=None) -> set[str]:
    """
    Populates and caches all valid usernames for this bot from:
    1. MTProto `client.me` (`me.username` + Fragment collectible `me.usernames`)
    2. Official Telegram Bot API `getMe` (always exposes active bot username)
    3. Optional `BOT_USERNAMES` environment variable
    """
    if me is None:
        me = getattr(client, "me", None)
        if me is None:
            try:
                me = await client.get_me()
                client.me = me
            except Exception as e:
                logger.warning("Could not fetch client.get_me() for username cache: %s", e)

    usernames, primary = _extract_usernames_from_user(me)

    # Also query Bot API `getMe` so Fragment collectible / secondary usernames are never missed
    try:
        bot_api_me = await call_bot_api("getMe", {})
        if isinstance(bot_api_me, dict):
            api_uname = bot_api_me.get("username")
            if isinstance(api_uname, str) and api_uname.strip():
                clean = api_uname.strip().lstrip("@")
                usernames.add(clean.casefold())
                if primary is None:
                    primary = clean
    except Exception as e:
        logger.debug("Bot API getMe lookup skipped: %s", e)

    for env_uname in BOT_USERNAMES:
        clean = env_uname.strip().lstrip("@")
        if clean:
            usernames.add(clean.casefold())
            if primary is None:
                primary = clean

    # Ensure `client.me.username` has a sensible fallback if MTProto left it None
    if me is not None and not getattr(me, "username", None) and primary:
        try:
            me.username = primary
        except Exception:
            pass

    client._cached_bot_usernames = usernames
    client._cached_bot_usernames_ts = time.monotonic()
    if primary:
        client._primary_bot_username = primary

    return usernames


async def get_bot_usernames(client: Client) -> set[str]:
    """Returns cached lowercase bot usernames, refreshing lazily if absent or expired."""
    cached = getattr(client, "_cached_bot_usernames", None)
    cached_ts = getattr(client, "_cached_bot_usernames_ts", 0.0)
    if cached and (time.monotonic() - cached_ts) < _CACHE_TTL_SECONDS:
        return cached
    return await refresh_bot_usernames(client)


def get_primary_bot_username(client: Client, fallback: str = "WordGridGameBot") -> str:
    """Returns the bot's primary display username (including collectible usernames)."""
    cached_primary = getattr(client, "_primary_bot_username", None)
    if cached_primary:
        return cached_primary

    me = getattr(client, "me", None)
    _, primary = _extract_usernames_from_user(me)
    if primary:
        return primary

    if BOT_USERNAMES:
        return BOT_USERNAMES[0]

    return fallback


def bot_command(
    commands: str | Iterable[str],
    prefixes: str | Iterable[str] = "/",
    case_sensitive: bool = False,
):
    """
    Drop-in replacement for `pyrogram.filters.command` that properly matches
    `/cmd` AND `/cmd@BotUsername` in groups — including bots with Fragment
    collectible usernames (`me.usernames`) or multiple active usernames.
    """
    cmd_list = [commands] if isinstance(commands, str) else list(commands)
    target_cmds = {c if case_sensitive else c.casefold() for c in cmd_list}

    prefix_list = [prefixes] if isinstance(prefixes, str) else list(prefixes)
    prefix_tuple = tuple(prefix_list)

    async def _filter(_, client: Client, message: Message) -> bool:
        text = message.text or message.caption
        if not text:
            return False

        stripped = text.strip()
        if not stripped:
            return False

        parts = stripped.split()
        if not parts:
            return False

        head = parts[0]
        matched_prefix = None
        for p in prefix_tuple:
            if head.startswith(p):
                matched_prefix = p
                break
        if matched_prefix is None:
            return False

        raw_cmd = head[len(matched_prefix):]
        if not raw_cmd:
            return False

        if "@" in raw_cmd:
            cmd_name, mentioned_username = raw_cmd.split("@", 1)
            mentioned_clean = mentioned_username.strip().lstrip("@").casefold()
            if not mentioned_clean:
                return False
            valid_usernames = await get_bot_usernames(client)
            if not valid_usernames or mentioned_clean not in valid_usernames:
                return False
        else:
            cmd_name = raw_cmd

        normalized_cmd = cmd_name if case_sensitive else cmd_name.casefold()
        if normalized_cmd not in target_cmds:
            return False

        # Preserve Pyrogram's exact `message.command` structure: [cmd, arg1, arg2, ...]
        message.command = [normalized_cmd, *parts[1:]]
        return True

    return filters.create(_filter, name="BotCommandFilter")
