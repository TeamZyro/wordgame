import inspect
from pyrogram.types import InlineKeyboardButton

# ============================================================================
# KURIGRAM PREMIUM EMOJI REGISTRY (User's Verified Custom Emoji Pack)
# ============================================================================

# Raw custom emoji IDs (for `icon_custom_emoji_id` on InlineKeyboardButton & Bot API)
ID_MIC = "5897554554894946515"
ID_MIC_OFF = "5897853622057700958"
ID_SPEAKER = "5890997763331591703"
ID_SPEAKER_OFF = "5890838600433536921"
ID_MUSIC = "5891249688933305846"
ID_MUSIC_OFF = "5890937586544807413"
ID_PLAY = "5900130736408629854"
ID_STOP = "5996789164383669947"
ID_QUEUE = "5915480455603295660"
ID_ROBOT = "5258093637450866522"
ID_SEARCH = "5874960879434338403"
ID_SHARE = "5832251986635920010"
ID_PIN = "5276310904445612311"
ID_SETTINGS = "6032742198179532882"
ID_SKIP = "5292270487521483627"
ID_TIMER = "5258258882022612173"
ID_LOADING = "6113844439292054570"
ID_GIFT = "5264710902153767489"
ID_LINK = "5240491147779907309"
ID_MAIL = "5253742260054409879"
ID_YT = "5341357385279612709"
ID_CROSS = "5454350746407419714"
ID_CLOCK24 = "5366043289633962337"
ID_HOURGLASS = "5373221902267457807"
ID_MEGAPHONE = "4992560350982309130"
ID_GIFT_OUT = "5985472565508838112"
ID_WARN = "5881702736843511327"
ID_BAN = "5886496611835581345"
ID_USER = "5886412370347036129"
ID_COMPOSE = "5985774024968379294"
ID_PENCIL = "5879841310902324730"
ID_FILE = "5257965810634202885"
ID_DOWNLOAD = "6037157012242960559"
ID_LIVE = "5778335621491723621"
ID_PLAY_OUT = "5775981206319402773"
ID_LOOP = "5877410604225924969"
ID_BOLT = "5843553939672274145"
ID_REFRESH = "5845943483382110702"
ID_STATS = "5933629020301169337"
ID_ADD = "5359529383319084413"
ID_NOTE = "5258334469152054985"
ID_SAVE = "5963087934696459905"
ID_CHECK = "5823396554345549784"
ID_NEW = "5886306834410640699"
ID_WAVE = "5260249440450520061"
ID_ANIME_CUTE = "5870874364081082158"
ID_ANIME_COOL = "5870896319953899581"
ID_BEST = "5251215200081698759"
ID_VERIFIED = "5357069174512303778"
ID_CHAT = "5884179047482659474"
ID_GRID = "5226513232549664618"
ID_TRASH = "5258130763148172425"
ID_CLOVER = "6172537761552142514"
ID_CROWN = "5807868868886009920"
ID_LEVELUP = "5463122435425448565"
ID_TOP = "5463071033256848094"
ID_GAME = "5938413566624272793"


def tg_emoji(emoji_id: str, fallback: str) -> str:
    return f'<tg-emoji emoji-id="{emoji_id}">{fallback}</tg-emoji>'


# Ready-to-use HTML `<tg-emoji>` tags
E_PLAY = tg_emoji(ID_PLAY, "🎞")
E_STOP = tg_emoji(ID_STOP, "🎞")
E_ROBOT = tg_emoji(ID_ROBOT, "🤖")
E_SEARCH = tg_emoji(ID_SEARCH, "🔎")
E_SHARE = tg_emoji(ID_SHARE, "➡️")
E_PIN = tg_emoji(ID_PIN, "👇")
E_SETTINGS = tg_emoji(ID_SETTINGS, "⚙")
E_SKIP = tg_emoji(ID_SKIP, "↖️")
E_TIMER = tg_emoji(ID_TIMER, "⏲")
E_LOADING = tg_emoji(ID_LOADING, "⏳")
E_GIFT = tg_emoji(ID_GIFT, "🎁")
E_LINK = tg_emoji(ID_LINK, "😛")
E_MAIL = tg_emoji(ID_MAIL, "✉️")
E_CROSS = tg_emoji(ID_CROSS, "❌")
E_CLOCK24 = tg_emoji(ID_CLOCK24, "🕘")
E_HOURGLASS = tg_emoji(ID_HOURGLASS, "⏳")
E_MEGAPHONE = tg_emoji(ID_MEGAPHONE, "📣")
E_GIFT_OUT = tg_emoji(ID_GIFT_OUT, "🎁")
E_WARN = tg_emoji(ID_WARN, "⚠️")
E_BAN = tg_emoji(ID_BAN, "👤")
E_USER = tg_emoji(ID_USER, "👤")
E_COMPOSE = tg_emoji(ID_COMPOSE, "🖊")
E_PENCIL = tg_emoji(ID_PENCIL, "✏️")
E_FILE = tg_emoji(ID_FILE, "📁")
E_LIVE = tg_emoji(ID_LIVE, "📷")
E_PLAY_OUT = tg_emoji(ID_PLAY_OUT, "🎞")
E_LOOP = tg_emoji(ID_LOOP, "🔄")
E_BOLT = tg_emoji(ID_BOLT, "⚡️")
E_REFRESH = tg_emoji(ID_REFRESH, "🔄")
E_STATS = tg_emoji(ID_STATS, "📊")
E_ADD = tg_emoji(ID_ADD, "➕")
E_CHECK = tg_emoji(ID_CHECK, "✔️")
E_NEW = tg_emoji(ID_NEW, "🆕")
E_WAVE = tg_emoji(ID_WAVE, "🤚")
E_ANIME_CUTE = tg_emoji(ID_ANIME_CUTE, "😉")
E_ANIME_COOL = tg_emoji(ID_ANIME_COOL, "😄")
E_BEST = tg_emoji(ID_BEST, "👑")
E_VERIFIED = tg_emoji(ID_VERIFIED, "✅")
E_CHAT = tg_emoji(ID_CHAT, "💬")
E_GRID = tg_emoji(ID_GRID, "🔢")
E_TRASH = tg_emoji(ID_TRASH, "🗑")
E_CLOVER = tg_emoji(ID_CLOVER, "🍀")
E_CROWN = tg_emoji(ID_CROWN, "👑")
E_LEVELUP = tg_emoji(ID_LEVELUP, "⬆️")
E_TOP = tg_emoji(ID_TOP, "🔝")
E_GAME = tg_emoji(ID_GAME, "🎮")

# Detect Kurigram 2.2.27+ `icon_custom_emoji_id` support on InlineKeyboardButton
try:
    _BTN_PARAMS = set(inspect.signature(InlineKeyboardButton.__init__).parameters.keys())
except Exception:
    _BTN_PARAMS = set()

SUPPORTS_BTN_ICON = "icon_custom_emoji_id" in _BTN_PARAMS


def make_button(
    text: str,
    *,
    callback_data: str | None = None,
    url: str | None = None,
    switch_inline_query: str | None = None,
    icon_id: str | None = None,
    fallback_prefix: str = "",
) -> InlineKeyboardButton:
    """
    Creates a Kurigram/Pyrogram InlineKeyboardButton.
    Uses `icon_custom_emoji_id` (str) natively on Kurigram 2.2.27+,
    or gracefully prepends `fallback_prefix` on older runtimes.
    """
    kwargs: dict = {}
    if callback_data is not None:
        kwargs["callback_data"] = callback_data
    if url is not None:
        kwargs["url"] = url
    if switch_inline_query is not None:
        kwargs["switch_inline_query"] = switch_inline_query

    if icon_id and SUPPORTS_BTN_ICON:
        label = text if text else "\u2060"
        kwargs["icon_custom_emoji_id"] = str(icon_id)
    else:
        if text:
            label = f"{fallback_prefix} {text}".strip() if fallback_prefix else text
        else:
            label = fallback_prefix or "•"

    return InlineKeyboardButton(label, **kwargs)


def make_api_button(
    text: str,
    *,
    callback_data: str | None = None,
    url: str | None = None,
    switch_inline_query: str | None = None,
    icon_id: str | None = None,
    style: str | None = None,
) -> dict:
    """
    Creates a Telegram Bot API 9.4+ / 10.3 InlineKeyboardButton dict supporting
    both `icon_custom_emoji_id` and `style` ("primary", "success", "danger").
    """
    btn: dict = {"text": text if text else "\u2060"}
    if callback_data is not None:
        btn["callback_data"] = callback_data
    if url is not None:
        btn["url"] = url
    if switch_inline_query is not None:
        btn["switch_inline_query"] = switch_inline_query
    if icon_id:
        btn["icon_custom_emoji_id"] = str(icon_id)
    if style:
        btn["style"] = style
    return btn
