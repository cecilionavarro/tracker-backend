from datetime import datetime, timedelta, timezone

from bson import ObjectId

from app.core.database import notes_collection, sessions_collection

# Allows for a browser clock that runs slightly ahead when someone picks "now".
FUTURE_TOLERANCE = timedelta(minutes=1)


class NoteError(Exception):
    def __init__(self, message: str, status_code: int = 422):
        super().__init__(message)
        self.status_code = status_code


def note_serial(note: dict) -> dict:
    return {
        "id": str(note["_id"]),
        "session_id": str(note["session_id"]) if note.get("session_id") else None,
        "text": note["text"],
        "at": note["at"],
        "created_at": note["created_at"],
        "updated_at": note["updated_at"],
    }


class NoteService:
    def __init__(self):
        pass

    def _clean_text(self, text: str) -> str:
        cleaned = text.strip()
        if not cleaned:
            raise NoteError("Write something first.")
        return cleaned

    def _clean_time(self, at: datetime | None, now: datetime) -> datetime:
        if at is None:
            return now
        at = at.astimezone(timezone.utc)
        if at > now + FUTURE_TOLERANCE:
            raise NoteError("Notes can't be in the future.")
        return min(at, now)

    async def _session_containing(self, user_id: str, at: datetime) -> dict | None:
        # The session that was running at that moment, if any.
        return await sessions_collection.find_one(
            {
                "user_id": ObjectId(user_id),
                "start_time": {"$lte": at},
                "$or": [{"end_time": {"$gte": at}}, {"end_time": None}],
            },
            sort=[("start_time", -1)],
        )

    async def _resolve_session(self, user_id: str, at: datetime, session_id: str | None, now: datetime):
        if session_id is None:
            session = await self._session_containing(user_id, at)
            return session["_id"] if session else None

        session = (
            await sessions_collection.find_one({"_id": ObjectId(session_id), "user_id": ObjectId(user_id)})
            if ObjectId.is_valid(session_id) else None
        )
        if not session:
            raise NoteError("Session not found.", status_code=404)
        end = session.get("end_time") or now
        if not session["start_time"] - FUTURE_TOLERANCE <= at <= end + FUTURE_TOLERANCE:
            raise NoteError("Pick a time during this session.")
        return session["_id"]

    async def _session_after_move(self, user_id: str, note: dict, at: datetime, now: datetime):
        # A note stays in its own session while the new time still falls in it,
        # with the same minute of leeway as adding one. The time field has no
        # seconds, so saving a note from a session's first minute could
        # otherwise land a few seconds before the session and drop out of it.
        if note.get("session_id"):
            session = await sessions_collection.find_one({"_id": note["session_id"], "user_id": ObjectId(user_id)})
            if session:
                end = session.get("end_time") or now
                if session["start_time"] - FUTURE_TOLERANCE <= at <= end + FUTURE_TOLERANCE:
                    return session["_id"]
        return await self._resolve_session(user_id, at, None, now)

    async def create_note(self, user_id: str, data: dict) -> dict:
        now = datetime.now(timezone.utc)
        text = self._clean_text(data["text"])
        at = self._clean_time(data.get("at"), now)
        note = {
            "user_id": ObjectId(user_id),
            "session_id": await self._resolve_session(user_id, at, data.get("session_id"), now),
            "text": text,
            "at": at,
            "created_at": now,
            "updated_at": now,
        }
        result = await notes_collection.insert_one(note)
        note["_id"] = result.inserted_id
        return note_serial(note)

    async def _get(self, user_id: str, note_id: str) -> dict:
        note = (
            await notes_collection.find_one({"_id": ObjectId(note_id), "user_id": ObjectId(user_id)})
            if ObjectId.is_valid(note_id) else None
        )
        if not note:
            raise NoteError("Note not found.", status_code=404)
        return note

    async def update_note(self, user_id: str, note_id: str, changes: dict) -> dict:
        note = await self._get(user_id, note_id)
        now = datetime.now(timezone.utc)
        updates = {"updated_at": now}
        if "text" in changes:
            updates["text"] = self._clean_text(changes["text"])
        if "at" in changes:
            updates["at"] = self._clean_time(changes["at"], now)
            # A new time can move the note into a different session.
            updates["session_id"] = await self._session_after_move(user_id, note, updates["at"], now)
        await notes_collection.update_one({"_id": note["_id"]}, {"$set": updates})
        note.update(updates)
        return note_serial(note)

    async def delete_note(self, user_id: str, note_id: str) -> dict:
        note = await self._get(user_id, note_id)
        await notes_collection.delete_one({"_id": note["_id"]})
        return {"id": str(note["_id"]), "session_id": str(note["session_id"]) if note.get("session_id") else None}

    async def list_session_notes(self, user_id: str, session_id: str) -> list[dict]:
        if not ObjectId.is_valid(session_id):
            raise NoteError("Session not found.", status_code=404)
        notes = await notes_collection.find(
            {"user_id": ObjectId(user_id), "session_id": ObjectId(session_id)}
        ).sort("at", 1).to_list(length=None)
        return [note_serial(note) for note in notes]

    async def summarize_sessions(self, session_ids: list) -> dict[str, dict]:
        # Each session's note count and most recent note, for the sessions table.
        if not session_ids:
            return {}
        cursor = await notes_collection.aggregate([
            {"$match": {"session_id": {"$in": session_ids}}},
            {"$sort": {"at": -1}},
            {"$group": {"_id": "$session_id", "count": {"$sum": 1}, "latest": {"$first": "$text"}}},
        ])
        return {str(row["_id"]): row for row in await cursor.to_list(length=None)}

    async def detach_session(self, session_id) -> None:
        # Deleting a session keeps its notes in the work log, standing alone.
        await notes_collection.update_many({"session_id": session_id}, {"$set": {"session_id": None}})


note_service = NoteService()
