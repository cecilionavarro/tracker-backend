from pymongo import AsyncMongoClient
from app.core.config import settings

mongo_client = AsyncMongoClient(settings.MONGO_URI)
db = mongo_client[settings.DB_NAME]

users_collection = db["users"]
sessions_collection = db["sessions"]
events_collection = db["events"]