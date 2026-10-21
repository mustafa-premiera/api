"""Translate DynamoDB Streams records into activity items."""
from datetime import datetime

from boto3.dynamodb.types import TypeDeserializer

_deser = TypeDeserializer()
TTL_SECONDS = 30 * 86400


def _plain(image):
    return {k: _deser.deserialize(v) for k, v in (image or {}).items()}


def to_activity(record: dict, now: datetime) -> dict | None:
    ddb = record["dynamodb"]
    keys = _plain(ddb["Keys"])
    old = _plain(ddb.get("OldImage"))
    new = _plain(ddb.get("NewImage"))
    name = record["eventName"]
    if name == "INSERT":
        action, src = "CREATED", new
    elif name == "MODIFY":
        done = old.get("status") != "DONE" and new.get("status") == "DONE"
        action, src = ("COMPLETED" if done else "UPDATED"), new
    elif name == "REMOVE":
        action, src = "DELETED", old
    else:
        return None
    return {
        "userId": keys["userId"],
        "sk": f"{now.isoformat(timespec='seconds')}#{record['eventID']}",
        "action": action,
        "todoId": keys["todoId"],
        "title": src.get("title", ""),
        "ttl": int(now.timestamp()) + TTL_SECONDS,
    }
