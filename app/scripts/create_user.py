import asyncio
from datetime import datetime, timezone

from app.core.database import users_collection
from app.models.users import UserModel


async def main():
    existing_user = await users_collection.find_one({"email": "test@test.com"})

    if existing_user:
        updated_user = UserModel(
            username="Samuel",
            email=existing_user["email"],
            role=existing_user.get("role", "user"),
            created_at=existing_user["created_at"],
        )

        await users_collection.update_one(
            {"email": "test@test.com"},
            {
                "$set": updated_user.model_dump(exclude={"id"})
            },
        )
        print("User updated")
    else:
        print("can't find user")


if __name__ == "__main__":
    asyncio.run(main())
