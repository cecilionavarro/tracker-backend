import asyncio
from datetime import datetime, timezone
from bson import ObjectId

from app.core.database import categories_collection
from app.models.category import CategoryModel


async def main():
    now = datetime.now(timezone.utc)

    existing_category = await categories_collection.find_one({"key": "gyrus"})

    if not existing_category:
        category = CategoryModel(
            group_id=ObjectId("69c2af380b699d12ba42404b"),
            key="gyrus",
            label="Gyrus",
            active=True,
            created_at=now,
            updated_at=now,
        )

        await categories_collection.insert_one(
            category.model_dump(exclude={"id"})
        )
        print("Category created")
    else:
        print("Category already exists")


if __name__ == "__main__":
    asyncio.run(main())
