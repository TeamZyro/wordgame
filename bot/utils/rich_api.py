import asyncio
import logging
import aiohttp
from bot.config import BOT_TOKEN

logger = logging.getLogger("WordGridBot.RichAPI")

BOT_API_BASE = f"https://api.telegram.org/bot{BOT_TOKEN}"
_http_session: aiohttp.ClientSession | None = None


def get_http_session() -> aiohttp.ClientSession:
    global _http_session
    if _http_session is None or _http_session.closed:
        timeout = aiohttp.ClientTimeout(total=15, connect=5)
        _http_session = aiohttp.ClientSession(timeout=timeout)
    return _http_session


async def close_http_session() -> None:
    global _http_session
    if _http_session is not None and not _http_session.closed:
        await _http_session.close()
        _http_session = None


async def call_bot_api(method: str, payload: dict, max_wait: int = 15) -> dict | None:
    """
    Calls the official Telegram Bot API 10.3 HTTP endpoint (`sendRichMessage`,
    `editMessageText` with `rich_message`, and styled `InlineKeyboardButton`s).
    Handles 429 retry_after automatically.
    """
    url = f"{BOT_API_BASE}/{method}"
    session = get_http_session()

    for attempt in range(2):
        try:
            async with session.post(url, json=payload) as resp:
                data = await resp.json(content_type=None)
                if data.get("ok"):
                    return data.get("result")

                err_code = data.get("error_code")
                desc = str(data.get("description", ""))
                if "message is not modified" in desc.lower():
                    return None

                if err_code == 429 and attempt == 0:
                    retry_after = int(
                        (data.get("parameters") or {}).get("retry_after", 3)
                    )
                    if retry_after <= max_wait:
                        await asyncio.sleep(retry_after + 0.5)
                        continue

                logger.warning("Bot API %s error (%s): %s", method, err_code, desc)
                return None
        except Exception as e:
            logger.debug("Bot API %s request exception: %s", method, e)
            return None
    return None


async def send_rich_message(
    chat_id: int | str,
    html_content: str,
    reply_markup: dict | None = None,
    message_thread_id: int | str | None = None,
    reply_to_message_id: int | None = None,
    disable_notification: bool = False,
) -> dict | None:
    """
    Sends a Telegram Bot API 10.3 RichMessage (`sendRichMessage`) supporting:
    - `<tg-button type="callback_data" style="success|danger|primary" data="...">` (`RichTextButton`)
    - `<tg-button-row>` (`InputRichBlockButtons`)
    - `<table bordered compact>` (`is_compact` on `InputRichBlockTable`)
    - `<details><summary>...</summary>...</details>` (`InputRichBlockExpandableBlockQuotation` / details)
    - `<h3>`, `<h4>`, `<p>`, `<blockquote>`, etc.
    """
    payload: dict = {
        "chat_id": chat_id,
        "rich_message": {
            "html": html_content,
        },
    }
    if message_thread_id and str(message_thread_id) != "general" and str(message_thread_id).isdigit():
        payload["message_thread_id"] = int(message_thread_id)
    if reply_to_message_id:
        payload["reply_parameters"] = {"message_id": int(reply_to_message_id)}
    if disable_notification:
        payload["disable_notification"] = True
    if reply_markup:
        payload["reply_markup"] = reply_markup

    return await call_bot_api("sendRichMessage", payload)


async def edit_rich_message(
    chat_id: int | str,
    message_id: int,
    html_content: str,
    reply_markup: dict | None = None,
) -> dict | None:
    """
    Edits an existing message into a Bot API 10.3 RichMessage via `editMessageText`
    with the `rich_message` parameter.
    """
    payload: dict = {
        "chat_id": chat_id,
        "message_id": int(message_id),
        "rich_message": {
            "html": html_content,
        },
    }
    if reply_markup:
        payload["reply_markup"] = reply_markup

    return await call_bot_api("editMessageText", payload)


async def send_styled_message(
    chat_id: int | str,
    text_html: str,
    reply_markup: dict | None = None,
    message_thread_id: int | str | None = None,
    reply_to_message_id: int | None = None,
    disable_notification: bool = True,
) -> dict | None:
    """
    Sends an HTML message via Bot API 10.3 supporting `style` ("primary", "success", "danger")
    and `disabled` on `InlineKeyboardButton` objects in `reply_markup`.
    """
    payload: dict = {
        "chat_id": chat_id,
        "text": text_html,
        "parse_mode": "HTML",
        "link_preview_options": {"is_disabled": True},
        "disable_notification": disable_notification,
    }
    if message_thread_id and str(message_thread_id) != "general" and str(message_thread_id).isdigit():
        payload["message_thread_id"] = int(message_thread_id)
    if reply_to_message_id:
        payload["reply_parameters"] = {"message_id": int(reply_to_message_id)}
    if reply_markup:
        payload["reply_markup"] = reply_markup

    return await call_bot_api("sendMessage", payload)


async def edit_styled_message(
    chat_id: int | str,
    message_id: int,
    text_html: str,
    reply_markup: dict | None = None,
) -> dict | None:
    """
    Edits an HTML message via Bot API 10.3 supporting `style` ("primary", "success", "danger")
    on `InlineKeyboardButton` objects in `reply_markup`.
    """
    payload: dict = {
        "chat_id": chat_id,
        "message_id": int(message_id),
        "text": text_html,
        "parse_mode": "HTML",
        "link_preview_options": {"is_disabled": True},
    }
    if reply_markup:
        payload["reply_markup"] = reply_markup

    return await call_bot_api("editMessageText", payload)
