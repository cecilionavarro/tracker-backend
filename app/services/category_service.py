import re
from datetime import datetime, timezone

from bson import ObjectId

from app.core.database import categories_collection, sessions_collection
from app.services.button_service import button_service

HEX_COLOR = re.compile(r"^#[0-9a-fA-F]{6}$")
MAX_TAG_LENGTH = 30


class CategoryError(Exception):
    def __init__(self, message: str, status_code: int = 422):
        super().__init__(message)
        self.status_code = status_code


def normalize_tag(tag: str) -> str:
    # Matches how the dashboard groups tags: "Non technical" is non_technical.
    return re.sub(r"[\s-]+", "_", tag.strip().lower())


def slugify(label: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", label.strip().lower()).strip("_") or "category"


class CategoryService:
    def __init__(self):
        pass

    def _button_map(self) -> dict[str, list[dict]]:
        # Which Pi buttons clock into each category, as assigned in the dashboard.
        return button_service.button_map()

    def _clean_tags(self, tags: list[str]) -> list[str]:
        cleaned = []
        for tag in tags:
            normalized = normalize_tag(tag)
            if not normalized:
                continue
            if len(normalized) > MAX_TAG_LENGTH:
                raise CategoryError(f"Tags can be at most {MAX_TAG_LENGTH} characters.")
            if normalized not in cleaned:
                cleaned.append(normalized)
        return cleaned

    def _clean_tag_colors(self, tag_colors: dict[str, str]) -> dict[str, str]:
        cleaned = {}
        for tag, color in tag_colors.items():
            normalized = normalize_tag(tag)
            if not normalized:
                continue
            if not HEX_COLOR.match(color or ""):
                raise CategoryError("Tag colors must be hex colors, like #3b82f6.")
            cleaned[normalized] = color.lower()
        return cleaned

    async def _ensure_unique_label(self, label: str, exclude_id: ObjectId | None = None) -> None:
        query = {"label": {"$regex": f"^{re.escape(label)}$", "$options": "i"}}
        if exclude_id is not None:
            query["_id"] = {"$ne": exclude_id}
        existing = await categories_collection.find_one(query)
        if existing:
            raise CategoryError(f"A category named {existing['label']} already exists.", status_code=409)

    async def _unique_key(self, label: str) -> str:
        base = slugify(label)
        key, suffix = base, 2
        while await categories_collection.find_one({"key": key}):
            key, suffix = f"{base}_{suffix}", suffix + 1
        return key

    def _serialize(self, category: dict, stats: dict | None, buttons: list[dict]) -> dict:
        stats = stats or {}
        defined = category.get("tags") or []
        used = {(tag or "").strip() for tag in stats.get("tags", [])}
        return {
            "id": str(category["_id"]),
            "label": category["label"],
            "color": category.get("color"),
            "tag_colors": category.get("tag_colors") or {},
            "tags": sorted(set(defined) | used | {""}),
            "defined_tags": defined,
            # Tags on existing sessions; the editor keeps these.
            "used_tags": sorted(used - {""}),
            "active": category.get("active", True) is not False,
            "session_count": stats.get("count", 0),
            "total_seconds": int(stats.get("seconds") or 0),
            "last_used_at": stats.get("last"),
            "buttons": buttons,
        }

    async def _get(self, category_id: str) -> dict:
        category = (
            await categories_collection.find_one({"_id": ObjectId(category_id)})
            if ObjectId.is_valid(category_id) else None
        )
        if not category:
            raise CategoryError("Category not found.", status_code=404)
        return category

    async def _stats(self, user_id: str, category_id: ObjectId | None = None) -> dict:
        match = {"user_id": ObjectId(user_id)}
        if category_id is not None:
            match["category_id"] = category_id
        cursor = await sessions_collection.aggregate([
            {"$match": match},
            {"$group": {
                "_id": "$category_id",
                "count": {"$sum": 1},
                # A running session counts its time so far.
                "seconds": {"$sum": {"$cond": [
                    {"$eq": [{"$ifNull": ["$end_time", None]}, None]},
                    {"$divide": [{"$subtract": ["$$NOW", "$start_time"]}, 1000]},
                    {"$ifNull": ["$elapsed_time", 0]},
                ]}},
                "last": {"$max": "$start_time"},
                "tags": {"$addToSet": "$tags"},
            }},
        ])
        return {str(row["_id"]): row for row in await cursor.to_list(length=None)}

    async def list_categories(self, user_id: str, include_archived: bool = False) -> list[dict]:
        query = {} if include_archived else {"active": {"$ne": False}}
        categories = await categories_collection.find(query).sort("label", 1).to_list(length=None)
        stats = await self._stats(user_id)
        buttons = self._button_map()
        return [
            self._serialize(category, stats.get(str(category["_id"])), buttons.get(str(category["_id"]), []))
            for category in categories
        ]

    async def create_category(self, user_id: str, data: dict) -> dict:
        label = data["label"].strip()
        if not label:
            raise CategoryError("Enter a name.")
        await self._ensure_unique_label(label)

        now = datetime.now(timezone.utc)
        tags = self._clean_tags(data.get("tags") or [])
        payload = {
            "key": await self._unique_key(label),
            "label": label,
            "color": (data.get("color") or "").lower() or None,
            "tags": tags,
            "tag_colors": {
                tag: color for tag, color in self._clean_tag_colors(data.get("tag_colors") or {}).items()
                if tag in tags
            },
            "active": True,
            "created_at": now,
            "updated_at": now,
        }
        result = await categories_collection.insert_one(payload)
        payload["_id"] = result.inserted_id
        return self._serialize(payload, None, [])

    async def update_category(self, user_id: str, category_id: str, changes: dict) -> dict:
        category = await self._get(category_id)
        buttons = self._button_map().get(str(category["_id"]), [])
        updates = {}

        if "label" in changes:
            label = changes["label"].strip()
            if not label:
                raise CategoryError("Enter a name.")
            await self._ensure_unique_label(label, exclude_id=category["_id"])
            updates["label"] = label

        if "color" in changes:
            updates["color"] = changes["color"].lower()

        if "tags" in changes:
            updates["tags"] = self._clean_tags(changes["tags"])

        if "tag_colors" in changes:
            updates["tag_colors"] = self._clean_tag_colors(changes["tag_colors"])

        if "active" in changes:
            if changes["active"] is False and buttons:
                pins = ", ".join(f"GPIO {button['pin']}" for button in buttons)
                raise CategoryError(
                    f"The {pins} button uses {category['label']}. Reassign it in Settings, under Buttons, first.",
                    status_code=409,
                )
            updates["active"] = changes["active"]

        if updates:
            updates["updated_at"] = datetime.now(timezone.utc)
            await categories_collection.update_one({"_id": category["_id"]}, {"$set": updates})
            category.update(updates)

        stats = await self._stats(user_id, category["_id"])
        return self._serialize(category, stats.get(str(category["_id"])), buttons)

    async def delete_category(self, user_id: str, category_id: str) -> dict:
        category = await self._get(category_id)
        buttons = self._button_map().get(str(category["_id"]), [])
        if buttons:
            pins = ", ".join(f"GPIO {button['pin']}" for button in buttons)
            raise CategoryError(
                f"The {pins} button uses {category['label']}. Reassign it in Settings, under Buttons, first.",
                status_code=409,
            )

        # Any session, from any user, keeps the category: its history needs the name and color.
        session_count = await sessions_collection.count_documents({"category_id": category["_id"]})
        if session_count:
            noun = "session uses" if session_count == 1 else "sessions use"
            raise CategoryError(
                f"{session_count} {noun} {category['label']}. Archive it instead to hide it and keep its history.",
                status_code=409,
            )

        await categories_collection.delete_one({"_id": category["_id"]})
        return {"id": str(category["_id"])}


category_service = CategoryService()
