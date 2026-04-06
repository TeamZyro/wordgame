import time
import asyncio
from pyrogram import Client, filters
from pyrogram.types import Message, InputMediaPhoto
from bot.utils.image_gen import create_new_game_state, render_grid_image
from bot.database.db import add_score, get_top_users

active_games = {}
group_rounds = {} # Stores current level per chat

def create_single_hint(word):
    if len(word) <= 2:
        return word[0] + " _ " * (len(word) - 1)
    
    middle = " _ " * (len(word) - 2)
    return f"{word[0]}{middle}{word[-1]}"

def get_caption(game_data):
    round_num = game_data.get("round", 1)
    time_limit = game_data.get("time_limit", 60)
    
    text = f"🧩 **Round {round_num} — RANDOM BOARD**\n"
    text += f"⚡ Time Limit: {time_limit}s  |  ⭐ Scale Combos!\n\n"
    
    words_dict = game_data["words"]
    for actual_word, info in words_dict.items():
        if info["found_by"]:
            text += f"✅ **{actual_word}** (*{info['found_by']}*)\n"
        else:
            hint = create_single_hint(actual_word)
            text += f"💡 `{hint}` ({len(actual_word)}L)\n"
            
    return text

async def execute_round(client: Client, chat_id: int, status_message=None):
    round_num = group_rounds.get(chat_id, 1)
    
    # Customized Explicit Progression Curve (Level 1 to 50+)
    if round_num <= 2:
        word_count = 2
        time_limit = 30
    elif round_num <= 4:
        word_count = 3
        time_limit = 40
    elif round_num <= 5:
        word_count = 4
        time_limit = 50
    elif round_num <= 8:
        word_count = 5 
        time_limit = 60
    elif round_num <= 12:
        word_count = 6
        time_limit = 70
    elif round_num <= 18:
        word_count = 7
        time_limit = 80
    elif round_num <= 25:
        word_count = 8
        time_limit = 90
    elif round_num <= 30:
        word_count = 9
        time_limit = 100
    elif round_num <= 35:
        word_count = 10
        time_limit = 110
    elif round_num <= 40:
        word_count = 11
        time_limit = 125
    elif round_num <= 45:
        word_count = 12
        time_limit = 140
    elif round_num <= 50:
        word_count = 13
        time_limit = 150
    else:  # Round 51 and beyond
        word_count = 14
        time_limit = 160
    
    if status_message is None:
        status_message = await client.send_message(chat_id, f"🔄 Preparing **Round {round_num}**...")
    else:
        try:
            await status_message.edit_text(f"🔄 Preparing **Round {round_num}**...")
        except:
            pass
        
    grid, words_info, theme_name = create_new_game_state(word_count)
    if not words_info:
        await status_message.edit_text("❌ Failed to build a puzzle. The round size might be too large.")
        return

    words_dict = {}
    for w in words_info.keys():
        w_upper = w.upper()
        words_dict[w_upper] = {
            "hint": create_single_hint(w_upper),
            "found_by": None
        }

    game_data = {
        "round": round_num,
        "grid": grid,
        "words_info": words_info,
        "words": words_dict,
        "found_words": [],
        "solved": False,
        "start_time": 0, # Will be set precisely after image delivery
        "time_limit": time_limit,
        "theme": theme_name
    }
    
    img_io = render_grid_image(grid, words_info, game_data["found_words"], round_num=round_num, theme_name=game_data["theme"])
    caption_text = get_caption(game_data)
    
    await status_message.delete()
    
    msg = await client.send_photo(
        chat_id=chat_id,
        photo=img_io,
        caption=caption_text
    )
    
    # Start timer exactly when message lands in chat
    game_data["start_time"] = time.time()
    game_data["message_id"] = msg.id
    active_games[chat_id] = game_data

@Client.on_message(filters.command(["game", "stopgame"]))
async def game_commands(client: Client, message: Message):
    if message.chat.type.name == "PRIVATE":
        await message.reply_text("⛔️ **Multiplayer Only!**\n\nArcade Mode is designed exclusively for group competition. Please add me to a group chat to play!", quote=True)
        return
        
    chat_id = message.chat.id
    cmd = message.command[0].lower()
    
    if cmd == "stopgame":
        if chat_id in active_games:
            active_games[chat_id]["solved"] = True
            group_rounds[chat_id] = 1 # Reset on stop
            await message.reply_text("🛑 Game forced stopped. Progress reset to Round 1.")
        else:
            await message.reply_text("No game running.")
        return

    if chat_id in active_games:
        active = active_games[chat_id]
        if not active.get("solved", True):
            time_elapsed = time.time() - active["start_time"]
            if time_elapsed < active["time_limit"]:
                time_left = int(active["time_limit"] - time_elapsed)
                await message.reply_text(f"⚠️ **Game is running!**\nSolve it or wait `{time_left}s` for it to timeout, or type `/stopgame`.")
                return
            else:
                active["solved"] = True
                
    # Manual start defaults to Round 1
    group_rounds[chat_id] = 1 
    m = await message.reply_text("🎮 Starting Arcade Word Grid!")
    await execute_round(client, chat_id, m)

@Client.on_message(filters.text & ~filters.bot & ~filters.command(["game", "stopgame", "panel", "leaderboard", "start", "help"]))
async def check_answer(client: Client, message: Message):
    chat_id = message.chat.id
    
    if chat_id in active_games:
        game = active_games[chat_id]
        
        if not game["solved"]:
            user_word = message.text.strip().upper()
            
            if user_word in game["words"]:
                
                if time.time() - game["start_time"] > game["time_limit"]:
                    game["solved"] = True
                    group_rounds[chat_id] = 1 # Penalty reset to Round 1
                    await message.reply_text(f"⏰ **TIME UP!**\nYou failed Round {game['round']}. Progress has been reset to Round 1.\nType /game to restart from the beginning.", quote=True)
                    return
                
                word_info = game["words"].get(user_word)
                if word_info["found_by"] is not None:
                    await message.reply_text(f"⚠️ `{user_word}` already found by {word_info['found_by']}!")
                    return

                word_info["found_by"] = message.from_user.first_name
                game["found_words"].append(user_word)
                
                # Points strictly constrained to 1 or 2 base, with a slow bonus bump.
                base_points = 1 if len(user_word) <= 4 else 2
                round_bonus = game['round'] // 10
                points = base_points + round_bonus
                
                await add_score(message.from_user.id, message.from_user.first_name, points)
                
                all_found = all(info["found_by"] is not None for info in game["words"].values())
                if all_found:
                    game["solved"] = True
                    time_taken = int(time.time() - game["start_time"])
                    next_round = game["round"] + 1
                    group_rounds[chat_id] = next_round
                    
                    await message.reply_text(f"🎊 **ROUND {game['round']} CLEARED!** 🎊\nAll words found in {time_taken}s.\n\n🔥 Advancing to **Round {next_round}** in 3 seconds...")
                    
                    # Auto progression
                    await asyncio.sleep(3)
                    await execute_round(client, chat_id)
                else:
                    await message.reply_text(f"🎉 **Yes!** {message.from_user.first_name} found `{user_word}`! (+{points} pts)", reply_to_message_id=message.id)

                try:
                    updated_img_io = render_grid_image(
                        grid=game["grid"], 
                        words_info=game["words_info"], 
                        found_words=game["found_words"],
                        round_num=game["round"],
                        theme_name=game["theme"]
                    )
                    media = InputMediaPhoto(media=updated_img_io, caption=get_caption(game))
                    await client.edit_message_media(chat_id=chat_id, message_id=game["message_id"], media=media)
                except Exception as e:
                    print(f"Failed to edit photo: {e}")

@Client.on_message(filters.command(["leaderboard"]))
async def leaderboard(client: Client, message: Message):
    top_users = await get_top_users(10)
    if not top_users:
        await message.reply_text("No one has played yet!")
        return
    text = "🏆 **Global Leaderboard** 🏆\n\n"
    for i, u in enumerate(top_users):
        name = u.get('first_name', 'Unknown')
        score = u.get('score', 0)
        user_id = u.get('user_id', 0)
        
        # Link name to user profile explicitly via tg:// protocol
        text += f"**{i+1}.** [{name}](tg://user?id={user_id}) - `{score}` points\n"
        
    await message.reply_text(text)
