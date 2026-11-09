def category_summary_serial(category: dict | None) -> dict | None:
    if not category:
        return None

    return {
        "id": str(category["_id"]),
        "label": category["label"],
        "color": category.get("color"),
        # Colors for individual tags, such as Pianiso's technical button.
        "tag_colors": category.get("tag_colors") or {},
    }
