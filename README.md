# 🎮 Word Grid Arcade + WordSeek Dual Bot (v3.0 — Pyrogram & Heroku Optimized)

All-in-one **Telegram Dual Word Game Bot** combining **3D Word Grid Arcade** and **WordSeek (Wordle 4L/5L/6L + Daily Mode)** inside a single **Pyrofork / Pyrogram + Motor (Async MongoDB) + Pillow** repository, optimized for **512MB RAM Heroku dynos** and **Python 3.12+**.

---

## ✨ Key Features

1. **Game 1 — 🧩 Word Grid Arcade (3D Word Search)**:
   - 5,600+ curated English dictionary words (`bot/utils/words.json`) with longest-first grid placement and 8 neon 3D themes.
   - Balanced 3D tile letter sizing (`44px`), per-chat async locks, unique `game_id` round timer cancellation, and debounced non-blocking `asyncio.to_thread` board updates.
   - Commands: `/game`, `/hint`, `/stopgame`.
2. **Game 2 — 🟩 WordSeek (Wordle 4, 5 & 6 Letters + Daily Mode)**:
   - Ported 100% from TypeScript/Grammy/Postgres/Redis into pure **Pyrogram + MongoDB** (`bot/plugins/wordseek.py` & `bot/utils/wordseek_engine.py`).
   - Supports **4-letter (`/new4`)**, **5-letter (`/new`, `/new5`, `/wordseek`)**, and **6-letter (`/new6`)** modes in groups and private chats.
   - Includes **WordSeek of the Day (`/daily` & `/pausedaily`)** in DM with Pillow-rendered dark Wordle board images, daily streaks, word definitions/IPA phonetics/example sentences (`commonWords.json`), and inline result sharing.
   - Includes 3-player vote-to-end (`/end`), interactive letter hint buttons (`🟩S`, `🟨T`, `🟥A`), group admin authorization (`/seekauth`), and forum topic controls (`/setgametopic`, `/unsetgametopic`, `/allowonlylen`).
3. **Compact Mobile Buttons & `@tgbot` View Consistency (`bot/utils/views.py`)**:
   - All inline buttons use short, mobile-friendly labels (`➕ Add to Group`, `🧩 Start Grid`, `🟩 Start Seek`, `💡 Hint`, `🔄 Board`, `🛑 Stop`, `🏆 Ranks`, `👤 Profile`, `📖 Help`, `⬅️ Back`).
   - Shared single-source-of-truth HTML view builders across all commands and callbacks.

---

## 🚀 Commands

| Command | Description |
| :--- | :--- |
| `/start` | Open the main Dual Word Game dashboard |
| `/game` | Start a 3D Word Grid Arcade round in a group |
| `/hint` | Reveal a letter hint in Word Grid |
| `/stopgame` | Stop the active Word Grid round |
| `/new` / `/wordseek` | Start a 5-letter WordSeek game (or `/new 4`, `/new 6`) |
| `/new4` / `/new5` / `/new6` | Start a 4, 5, or 6-letter WordSeek game |
| `/end` / `/endseek` | End the current WordSeek game (admin/starter or 3-player vote) |
| `/daily` / `/pausedaily` | Play or pause Daily WordSeek in Private Chat (DM) |
| `/score` / `/myscore` | View WordSeek scores & streaks (`/score [global\|group] [today\|week\|month\|all] [4\|5\|6]`) |
| `/profile` / `/rank` | View combined Word Grid + WordSeek player profile card |
| `/leaderboard` / `/top` | View interactive Dual Leaderboards (Word Grid & WordSeek) |
| `/seekauth` | Authorize group members to end WordSeek games without voting |
| `/setgametopic` / `/unsetgametopic` | Restrict games to specific forum topics |
| `/allowonlylen` | Set allowed WordSeek lengths in a topic (`/allowonlylen 5 4 6`) |
| `/id` | View chat, user, topic, and message IDs |
| `/panel` / `/admin` / `/stats` | Admin dashboard & live system stats (`SUDO_USERS` only) |
| `/ban` / `/unban` / `/transfer` | Global user moderation & score transfer (`SUDO_USERS` only) |
| `/broadcast` | Reply to any message to broadcast to all users & groups (`SUDO_USERS` only) |
