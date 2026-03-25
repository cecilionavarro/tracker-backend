# python -m app.scripts.create_category_groups
import asyncio
from datetime import datetime, timezone

from app.core.database import category_groups_collection
from app.models.category_group import CategoryGroupModel


async def main():
    now = datetime.now(timezone.utc)
    key = "personal"

    existing_group = await category_groups_collection.find_one({"key": key})

    if not existing_group:
        group = CategoryGroupModel(
            key=key,
            label="Personal",
            color="yellow",
            active=True,
            created_at=now,
            updated_at=now,
        )

        await category_groups_collection.insert_one(
            group.model_dump(exclude={"id"})
        )
        print(f"Category group {key} created")
    else:
        print(f"Category group {key} already exists")


if __name__ == "__main__":
    asyncio.run(main())
