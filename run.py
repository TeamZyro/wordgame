import asyncio
import logging
from pyrogram import Client
from pyrogram.enums import ParseMode
from bot.config import API_ID, API_HASH, BOT_TOKEN, PORT
from bot.database.db import init_db, close_db
from bot.utils.rich_api import close_http_session
from bot.utils.command_filter import refresh_bot_usernames, get_primary_bot_username

try:
    asyncio.get_event_loop()
except RuntimeError:
    asyncio.set_event_loop(asyncio.new_event_loop())

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logging.getLogger("pyrogram").setLevel(logging.WARNING)
logger = logging.getLogger("WordGridBot")


class Bot(Client):
    def __init__(self):
        super().__init__(
            name="WordGridGameBot",
            api_id=API_ID,
            api_hash=API_HASH,
            bot_token=BOT_TOKEN,
            plugins=dict(root="bot/plugins"),
            parse_mode=ParseMode.HTML,
            in_memory=True,
            workers=8,
            max_concurrent_transmissions=4,
        )
        self._health_server = None

    async def _start_health_server(self):
        if not PORT:
            return

        async def _handle_client(reader: asyncio.StreamReader, writer: asyncio.StreamWriter):
            try:
                await asyncio.wait_for(reader.read(512), timeout=2.0)
                body = b'{"status":"ok","bot":"WordGridGameBot"}'
                response = (
                    b"HTTP/1.1 200 OK\r\n"
                    b"Content-Type: application/json\r\n"
                    b"Content-Length: " + str(len(body)).encode() + b"\r\n"
                    b"Connection: close\r\n\r\n" + body
                )
                writer.write(response)
                await writer.drain()
            except Exception:
                pass
            finally:
                try:
                    writer.close()
                    await writer.wait_closed()
                except Exception:
                    pass

        try:
            self._health_server = await asyncio.start_server(_handle_client, "0.0.0.0", PORT)
            logger.info("Heroku health-check server listening on port %s", PORT)
        except Exception as e:
            logger.warning("Could not bind health-check port %s: %s", PORT, e)

    async def start(self, *args, **kwargs):
        await init_db()
        await self._start_health_server()
        await super().start(*args, **kwargs)
        me = await self.get_me()
        self.me = me
        usernames = await refresh_bot_usernames(self, me=me)
        primary_uname = get_primary_bot_username(self)
        logger.info(
            "Bot started as %s (@%s) [ID: %s] | Accepted usernames: %s",
            me.first_name,
            primary_uname,
            me.id,
            ", ".join(f"@{u}" for u in sorted(usernames)) or "none",
        )

    async def stop(self, *args, **kwargs):
        if self._health_server is not None:
            self._health_server.close()
            await self._health_server.wait_closed()
        await close_http_session()
        await close_db()
        await super().stop(*args, **kwargs)
        logger.info("Bot stopped cleanly.")


if __name__ == "__main__":
    bot = Bot()
    bot.run()
