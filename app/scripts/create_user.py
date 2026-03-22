# make sure you're in venv and in the root folder
# run `python -m app.scripts.create_user`

import asyncio
from datetime import datetime, timezone

from app.core.database import users_collection


async def main():
    existing_user = await users_collection.find_one({"email": "test@test.com"})

    if not existing_user:
        await users_collection.insert_one({
            "username": "test",
            "email": "test@test.com",
            "role": "user",
            "created_at": datetime.now(timezone.utc),
        })
        print("User created")
    else:
        print("User already exists")


if __name__ == "__main__":
    asyncio.run(main())
