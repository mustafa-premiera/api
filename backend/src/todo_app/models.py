"""Domain model: request validation and (de)serialisation helpers."""
import re
from datetime import date

STATUSES = ("OPEN", "DONE")
NO_DUE_DATE = "9999-12-31"
TITLE_MAX = 200
DESCRIPTION_MAX = 2000
_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
_ALLOWED = {"title", "description", "status", "dueDate"}
_PUBLIC = ("todoId", "title", "description", "status", "dueDate", "createdAt", "updatedAt")


class ValidationError(Exception):
    pass


def _title(value):
    if not isinstance(value, str):
        raise ValidationError("title must be a string")
    value = value.strip()
    if not 1 <= len(value) <= TITLE_MAX:
        raise ValidationError(f"title must be 1-{TITLE_MAX} characters")
    return value


def _description(value):
    if not isinstance(value, str):
        raise ValidationError("description must be a string")
    if len(value) > DESCRIPTION_MAX:
        raise ValidationError(f"description must be at most {DESCRIPTION_MAX} characters")
    return value


def _status(value):
    if value not in STATUSES:
        raise ValidationError("status must be OPEN or DONE")
    return value


def _due_date(value):
    if value is None:
        return None
    if not isinstance(value, str) or not _DATE_RE.match(value):
        raise ValidationError("dueDate must be YYYY-MM-DD")
    try:
        date.fromisoformat(value)
    except ValueError:
        raise ValidationError("dueDate is not a valid date") from None
    return value


_VALIDATORS = {
    "title": _title,
    "description": _description,
    "status": _status,
    "dueDate": _due_date,
}


def _check_body(body):
    if not isinstance(body, dict):
        raise ValidationError("body must be a JSON object")
    unknown = set(body) - _ALLOWED
    if unknown:
        raise ValidationError(f"unknown field(s): {', '.join(sorted(unknown))}")


def parse_create(body):
    _check_body(body)
    if "title" not in body:
        raise ValidationError("title is required")
    return {
        "title": _title(body["title"]),
        "description": _description(body.get("description", "")),
        "status": _status(body.get("status", "OPEN")),
        "dueDate": _due_date(body.get("dueDate")),
    }


def parse_update(body):
    _check_body(body)
    if not body:
        raise ValidationError("at least one field is required")
    return {k: _VALIDATORS[k](v) for k, v in body.items()}


def status_due(status, due_date):
    return f"{status}#{due_date or NO_DUE_DATE}"


def to_public(item):
    out = {k: item.get(k) for k in _PUBLIC}
    return out
