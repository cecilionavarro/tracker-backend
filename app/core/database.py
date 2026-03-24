from pymongo import AsyncMongoClient
from app.core.config import settings

mongo_client = AsyncMongoClient(
  settings.MONGO_URI,
  tz_aware=True,
)
db = mongo_client[settings.DB_NAME]

users_collection = db["users"]
sessions_collection = db["sessions"]
events_collection = db["events"]
categories_collection = db["categories"]
category_groups_collection = db["category_groups"]