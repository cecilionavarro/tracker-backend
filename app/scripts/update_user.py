# make sure you're in venv and in the root folder
# run `python -m app.scripts.update_user`

import asyncio
from app.core.database import users_collection


async def main():
    existing_user = await users_collection.find_one({"email": "test@test.com"})

    if existing_user:
        await users_collection.update_one(
            {"email": "test@test.com"},
            {
                "$set": {
                "username": "Samuel",
                }
            },
        )
        print("User updated")
    else:
        print("can't find user")


if __name__ == "__main__":
    asyncio.run(main())
