from datetime import datetime, timezone

from bson import ObjectId

from app.core.database import buttons_collection, categories_collection
from app.hardware.pins import BUTTON_CONFIGS
from app.schemas.category_schema import category_summary_serial
from app.services.session_service import session_service

# The buttons wired to the Pi, by GPIO number, with their physical header pin.
# What each one does is stored in MongoDB.
BUTTON_PINS = tuple(config["pin"] for config in BUTTON_CONFIGS)
PHYSICAL_PINS = {2: 3, 3: 5, 4: 7, 17: 11, 22: 15, 23: 16, 27: 13}
# "activity" clocks into a category and tag; the counters add one per press.
ACTIONS = ("activity", "pullup", "distraction", "none")


class ButtonError(Exception):
  def __init__(self, message: str, status_code: int = 422):
    super().__init__(message)
    self.status_code = status_code


def normalize_tag(tag: str) -> str:
  return "_".join(tag.strip().lower().replace("-", " ").split())


def get_action(assignment: dict) -> str:
  # Assignments saved before buttons had actions only clocked into categories.
  return assignment.get("action") or ("activity" if assignment.get("category_id") else "none")


class ButtonService:
  def __init__(self):
    # pin -> {"action": str, "category_id": str | None, "tags": str}, read on every press.
    self.assignments = {}

  def _defaults(self) -> dict:
    # The assignments in app/hardware/pins.py, used until changed in the dashboard.
    return {
      config["pin"]: {
        "action": config["action"],
        "category_id": session_service.resolve_category_id(config["category"]) if config["action"] == "activity" else None,
        "tags": config.get("tags", ""),
      }
      for config in BUTTON_CONFIGS
    }

  def use_defaults(self) -> None:
    self.assignments = self._defaults()

  async def load(self) -> None:
    # Stored assignments win; pins never saved start from pins.py and are saved.
    stored = {doc["pin"]: doc for doc in await buttons_collection.find({}).to_list(length=None)}
    defaults = self._defaults()
    now = datetime.now(timezone.utc)
    assignments = {}
    for pin in BUTTON_PINS:
      doc = stored.get(pin)
      if doc is None:
        default = defaults[pin]
        doc = {
          "pin": pin,
          "action": default["action"],
          "category_id": ObjectId(default["category_id"]) if default["category_id"] else None,
          "tags": default["tags"],
          "updated_at": now,
        }
        await buttons_collection.insert_one(doc)
      assignments[pin] = {
        "action": get_action(doc),
        "category_id": str(doc["category_id"]) if doc.get("category_id") else None,
        "tags": doc.get("tags", ""),
      }
    self.assignments = assignments

  def get(self, pin: int) -> dict | None:
    # The category a button clocks into, or None when it doesn't clock in.
    assignment = self.assignments.get(pin)
    if not assignment or get_action(assignment) != "activity" or not assignment["category_id"]:
      return None
    return {"category_id": assignment["category_id"], "tags": assignment["tags"]}

  def get_action(self, pin: int) -> str:
    # What a press does: "activity" only while the button has a category.
    assignment = self.assignments.get(pin)
    if not assignment:
      return "none"
    action = get_action(assignment)
    return "none" if action == "activity" and not assignment["category_id"] else action

  def button_map(self) -> dict[str, list[dict]]:
    # Which buttons clock into each category.
    buttons = {}
    for pin, assignment in sorted(self.assignments.items()):
      if get_action(assignment) == "activity" and assignment["category_id"]:
        buttons.setdefault(assignment["category_id"], []).append(
          {"pin": pin, "label": f"GPIO {pin}", "tags": assignment["tags"]}
        )
    return buttons

  async def list_buttons(self) -> list[dict]:
    ids = [ObjectId(a["category_id"]) for a in self.assignments.values() if a["category_id"]]
    categories = await categories_collection.find({"_id": {"$in": ids}}).to_list(length=None) if ids else []
    category_map = {str(category["_id"]): category for category in categories}
    return [
      {
        "pin": pin,
        "physical_pin": PHYSICAL_PINS.get(pin),
        "action": self.get_action(pin),
        "category": category_summary_serial(category_map.get(assignment["category_id"] or "")),
        "tags": assignment["tags"],
      }
      # In wiring order, the same as app/hardware/pins.py.
      for pin, assignment in sorted(self.assignments.items(), key=lambda item: BUTTON_PINS.index(item[0]))
    ]

  async def assign(self, pin: int, category_id: str | None, tags: str, action: str | None = None) -> dict:
    if pin not in BUTTON_PINS:
      raise ButtonError(f"GPIO {pin} isn't a button.", status_code=404)
    # Without an action, a category means clocking into it, as before actions existed.
    action = action or ("activity" if category_id else "none")
    if action not in ACTIONS:
      raise ButtonError(f"Unknown action {action}.")
    if action == "activity" and category_id is None:
      raise ButtonError("Pick a category for the button to clock into.")

    category = None
    if action == "activity":
      category = (
        await categories_collection.find_one({"_id": ObjectId(category_id)})
        if ObjectId.is_valid(category_id) else None
      )
      if not category:
        raise ButtonError("Unknown category.")
      if category.get("active") is False:
        raise ButtonError(f"{category['label']} is archived. Restore it first.")

    tag = normalize_tag(tags) if category else ""
    await buttons_collection.update_one(
      {"pin": pin},
      {"$set": {
        "action": action,
        "category_id": category["_id"] if category else None,
        "tags": tag,
        "updated_at": datetime.now(timezone.utc),
      }},
      upsert=True,
    )
    self.assignments[pin] = {"action": action, "category_id": str(category["_id"]) if category else None, "tags": tag}
    return {
      "pin": pin,
      "physical_pin": PHYSICAL_PINS.get(pin),
      "action": action,
      "category": category_summary_serial(category),
      "tags": tag,
    }


button_service = ButtonService()
