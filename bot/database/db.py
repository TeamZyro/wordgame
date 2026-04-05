from motor.motor_asyncio import AsyncIOMotorClient
from bot.config import MONGO_URI, DB_NAME

client = AsyncIOMotorClient(MONGO_URI)
db = client[DB_NAME]
users_collection = db['users']
groups_collection = db['groups']

async def add_user(user_id: int, username: str, first_name: str):
    if not await users_collection.find_one({'user_id': user_id}):
        await users_collection.insert_one({
            'user_id': user_id,
            'username': username,
            'first_name': first_name,
            'score': 0,
            'games_played': 0
        })

async def add_group(chat_id: int, title: str):
    if not await groups_collection.find_one({'chat_id': chat_id}):
        await groups_collection.insert_one({
            'chat_id': chat_id,
            'title': title
        })

async def add_score(user_id: int, first_name: str, points: int):
    await users_collection.update_one(
        {'user_id': user_id},
        {
            '$inc': {'score': points, 'games_played': 1},
            '$set': {'first_name': first_name}
        },
        upsert=True
    )

async def get_user(user_id: int):
    return await users_collection.find_one({'user_id': user_id})

async def get_top_users(limit: int = 10):
    cursor = users_collection.find().sort('score', -1).limit(limit)
    return await cursor.to_list(length=limit)

async def get_total_users():
    return await users_collection.count_documents({})

async def get_total_groups():
    return await groups_collection.count_documents({})

async def get_all_users():
    cursor = users_collection.find({}, {'user_id': 1})
    return await cursor.to_list(length=None)

async def get_all_groups():
    cursor = groups_collection.find({}, {'chat_id': 1})
    return await cursor.to_list(length=None)
