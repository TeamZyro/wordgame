# 🧩 Word Grid Arcade Bot (v2.0 — Heroku Optimized)

Fast-paced **3D Word Search Arcade Telegram Bot** built with **Pyrofork / Pyrogram**, **Motor (Async MongoDB)**, and **Pillow**, engineered for **Heroku 512MB RAM dynos** and **Python 3.12+**.

---

## ✨ What's New in v2.0

1. **Curated 1,800+ Pure Word Dictionary (`bot/utils/words.json`)**:
   - Removed all broken web-log acronyms (`UTC`, `PDF`, `USB`, `DVD`, `PHP`, `SQL`, `III`, `DER`, `LIB`, etc.), proper names, and junk tokens.
   - Balanced 3-to-8 letter vocabulary across Nature, Animals, Space, Gaming, Food, Science, Music, and Everyday Objects.
   - Smart **Longest-First Word Placement** with 25-pass best-attempt selection and substring collision avoidance.
2. **Complete Cooldown, Lock & Timer Engine (`bot/utils/cooldown.py` & `bot/plugins/game.py`)**:
   - **Fixed Premature Round Timeout Bug**: Every round uses a unique `game_id` token and cancels previous `timeout_task` / `next_round_task` handles immediately when a round is cleared, stopped, or restarted.
   - **Per-Chat & Per-User Async Locks**: Eliminates race conditions on simultaneous word guesses and button clicks.
   - **Debounced Non-Blocking Board Updates**: Renders 3D Pillow boards inside `asyncio.to_thread` with `@lru_cache` fonts and coalesces rapid word finds to prevent Telegram `FloodWait`.
   - **Interactive Hint & Board Refresh System**: Added `/hint` command + `💡 Hint`, `🔄 Refresh Board`, and `🛑 Stop Game` inline buttons with dedicated cooldowns.
3. **Rich HTML UI & 100% View Consistency (`bot/utils/views.py`)**:
   - Full `ParseMode.HTML` formatting with `<blockquote>`, `<code>`, safe `html.escape()`, and stylized Unicode name normalization.
   - Shared single-source-of-truth view builders for `/start`, `/help`, `/profile` (`/rank`, `/stats`, `/me`), `/leaderboard` (`/top`), and `/panel` (`/admin`) so command messages and `Back` / `Refresh` / tab callbacks stay 100% identical.
4. **Heroku Dyno Optimization (`run.py`, `Procfile`, `bot/database/db.py`)**:
   - Supports both `worker` and `web` dynos (automatically binds a lightweight health-check responder on `$PORT` if present to prevent Heroku `R10` boot timeouts).
   - Uses `in_memory=True` Pyrogram session, bounded Motor connection pool (`maxPoolSize=20`), MongoDB indexes, and 15-second TTL leaderboard caching.

---

## 🚀 Commands

| Command | Description |
| :--- | :--- |
| `/start` | Open the main Arcade dashboard |
| `/game` | Start a new Word Grid Arcade session in a group |
| `/hint` | Unlock a letter hint for an unfound word (up to 3 per round) |
| `/stopgame` | Stop the active group game and reset to Round 1 |
| `/profile` / `/rank` | View your player profile card, global rank, and tier |
| `/leaderboard` / `/top` | View Top 10 Global Players & Top 10 Active Groups |
| `/help` | View game rules and scoring breakdown |
| `/panel` / `/admin` | Admin control panel & live stats (`SUDO_USERS` only) |
| `/broadcast` | Reply to any message to broadcast to all users & groups (`SUDO_USERS` only) |

---

## ⚙️ Heroku Deployment

1. Push this repository to GitHub.
2. Connect your GitHub repo on Heroku Dashboard (or use the `app.json` config).
3. Set Config Vars in Heroku Settings:
   - `API_ID`
   - `API_HASH`
   - `BOT_TOKEN`
   - `MONGO_URI`
   - `DB_NAME` (default: `WordGridBotDB`)
   - `SUDO_USERS` (comma-separated admin Telegram IDs)
4. Enable the `worker` dyno (or `web` dyno — both are supported automatically!).
