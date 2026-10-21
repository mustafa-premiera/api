"""API Gateway proxy helpers."""
import json
from decimal import Decimal

from .models import ValidationError


def _default(o):
    if isinstance(o, Decimal):
        return int(o) if o == o.to_integral_value() else float(o)
    raise TypeError(f"Not serializable: {type(o).__name__}")


def user_id(event):
    return event["requestContext"]["authorizer"]["claims"]["sub"]


def json_response(status, body):
    return {
        "statusCode": status,
        "headers": {"Content-Type": "application/json", "Cache-Control": "no-store"},
        "body": "" if body is None else json.dumps(body, default=_default),
    }


def parse_json_body(event):
    try:
        body = json.loads(event.get("body") or "")
    except (ValueError, TypeError):
        raise ValidationError("body must be valid JSON") from None
    if not isinstance(body, dict):
        raise ValidationError("body must be a JSON object")
    return body


def not_found():
    return json_response(404, {"message": "Todo not found"})


def bad_request(e):
    return json_response(400, {"message": str(e)})
