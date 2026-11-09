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
# One document per pull-up, so totals can be counted for any day or week.
pullups_collection = db["pullups"]
# Timestamped work-log notes, linked to the session they happened in, if any.
notes_collection = db["notes"]
# Which category each Pi activity button clocks into, editable from the dashboard.
buttons_collection = db["buttons"]
