import asyncio
from datetime import datetime, timezone
from bson import ObjectId

from app.core.database import categories_collection
from app.models.category import CategoryModel


async def main():
    now = datetime.now(timezone.utc)

    key = "toycon"

    existing_category = await categories_collection.find_one({"key": key})

    if not existing_category:
        category = CategoryModel(
            group_id="69c2af380b699d12ba42404b",
            key=key,
            label="Toycon",
            active=True,
            created_at=now,
            updated_at=now,
        )
        payload = category.model_dump(exclude={"id"})
        payload["group_id"] = ObjectId(payload["group_id"])

        await categories_collection.insert_one(payload)
        print(f"Category {key} created")
    else:
        print(f"Category {key} already exists")


if __name__ == "__main__":
    asyncio.run(main())
