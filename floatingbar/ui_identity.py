"""Content-free UI Automation identities shared by conversation pickers.

Only structural fields are retained: control type, class, framework, and a
bounded ancestor chain. UIA AutomationId is intentionally excluded because
desktop applications may populate it with user-facing names or other
context-bearing strings.
"""

def _normalized_parts(values) -> tuple[str, ...]:
    return tuple(
        str(value).strip()
        for value in values
        if value not in (None, "")
    )


def control_identity(element_info) -> tuple[str, ...] | None:
    """Return stable structural control metadata without AutomationId."""
    try:
        values = (
            getattr(element_info, "control_type", None),
            getattr(element_info, "class_name", None),
            getattr(element_info, "framework_id", None),
        )
    except Exception:
        return None
    normalized = _normalized_parts(values)
    return normalized or None


def ancestor_identity(item, max_depth: int = 3) -> tuple[str, ...] | None:
    """Return a bounded, content-free ancestor structure."""
    parts: list[str] = []
    current = item
    for depth in range(1, max(1, int(max_depth)) + 1):
        try:
            current = current.parent()
            identity = control_identity(current.element_info)
        except Exception:
            break
        if identity:
            parts.extend((f"ancestor{depth}", *identity))
    return tuple(parts) or None


__all__ = ["ancestor_identity", "control_identity"]
