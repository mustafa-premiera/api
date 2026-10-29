import importlib
from datetime import datetime, timezone

import pytest

from todo_app.stream import to_activity

NOW = datetime(2026, 10, 21, 12, 0, 0, tzinfo=timezone.utc)
KEYS = {"userId": {"S": "u1"}, "todoId": {"S": "t1"}}


def img(title, status="OPEN"):
    return {**KEYS, "title": {"S": title}, "status": {"S": status}}


def rec(name, eid="e1", **images):
    return {
        "eventID": eid,
        "eventName": name,
        "dynamodb": {"Keys": KEYS, "SequenceNumber": f"seq-{eid}", **images},
    }


def check(out, action, title):
    assert out == {
        "userId": "u1",
        "sk": "2026-10-21T12:00:00+00:00#e1",
        "action": action,
        "todoId": "t1",
        "title": title,
        "ttl": int(NOW.timestamp()) + 30 * 86400,
    }


def test_created():
    check(to_activity(rec("INSERT", NewImage=img("A")), NOW), "CREATED", "A")


def test_updated():
    r = rec("MODIFY", OldImage=img("A"), NewImage=img("B"))
    check(to_activity(r, NOW), "UPDATED", "B")


def test_completed():
    r = rec("MODIFY", OldImage=img("A"), NewImage=img("A", "DONE"))
    check(to_activity(r, NOW), "COMPLETED", "A")


def test_deleted_uses_old_image():
    check(to_activity(rec("REMOVE", OldImage=img("A")), NOW), "DELETED", "A")


def test_handler_partial_batch(tables):
    from todo_app.handlers import stream_processor

    m = importlib.reload(stream_processor)
    good = rec("INSERT", eid="good", NewImage=img("A"))
    bad = {
        "eventID": "bad",
        "eventName": "INSERT",
        "dynamodb": {"SequenceNumber": "seq-bad", "NewImage": img("B")},
    }
    assert m.handler({"Records": [good, bad]}, None) == {
        "batchItemFailures": [{"itemIdentifier": "seq-bad"}]
    }
    items = tables[1].scan()["Items"]
    assert len(items) == 1 and items[0]["sk"].endswith("#good")
