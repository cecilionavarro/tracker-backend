from datetime import timezone

def individual_session_serial(session: dict) -> dict:
    start_time = session["start_time"]
    if start_time.tzinfo is None:
        start_time = start_time.replace(tzinfo=timezone.utc)

    end_time = session.get("end_time")
    if end_time and end_time.tzinfo is None:
        end_time = end_time.replace(tzinfo=timezone.utc)

    is_active = session.get("status") == "active" and end_time is None

    elapsed_time = session.get("elapsed_time")

    return {
        "id": str(session["_id"]),
        "category_id": str(session["category_id"]),
        "status": session["status"],
        "is_active": is_active,
        "start_time": start_time,
        "end_time": end_time,
        "elapsed_time": elapsed_time,
        "tags": session.get("tags", ""),
        "notes": session.get("notes", ""),
    }

def list_session_serial(sessions) -> list:
    return [individual_session_serial(session) for session in sessions]