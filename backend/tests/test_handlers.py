import importlib
import json

import pytest

NAMES = ["list_todos", "get_todo", "create_todo", "update_todo", "delete_todo", "list_activity"]


def event(sub, body=None, path=None, query=None):
    return {
        "requestContext": {"authorizer": {"claims": {"sub": sub}}},
        "body": body,
        "pathParameters": {"id": path} if path else None,
        "queryStringParameters": query,
    }


@pytest.fixture
def h(tables):
    mods = {}
    for n in NAMES:
        m = importlib.import_module(f"todo_app.handlers.{n}")
        mods[n] = importlib.reload(m)
    return mods, tables


def create(mods, sub, **fields):
    r = mods["create_todo"].handler(event(sub, json.dumps(fields)), None)
    assert r["statusCode"] == 201
    return json.loads(r["body"])


def test_create_then_list(h):
    mods, _ = h
    item = create(mods, "u1", title="Buy milk")
    assert "userId" not in item
    r = mods["list_todos"].handler(event("u1"), None)
    assert r["statusCode"] == 200
    assert r["headers"]["Cache-Control"] == "no-store"
    assert r["headers"]["Content-Type"] == "application/json"
    assert json.loads(r["body"])["items"] == [item]
    r2 = mods["list_todos"].handler(event("u2"), None)
    assert json.loads(r2["body"])["items"] == []


def test_list_status_filter(h):
    mods, _ = h
    create(mods, "u1", title="a")
    create(mods, "u1", title="b", status="DONE")
    r = mods["list_todos"].handler(event("u1", query={"status": "DONE", "v": "1"}), None)
    assert [i["title"] for i in json.loads(r["body"])["items"]] == ["b"]
    r = mods["list_todos"].handler(event("u1", query={"status": "foo"}), None)
    assert r["statusCode"] == 400


def test_get_update_delete_owner_and_other_user(h):
    mods, _ = h
    item = create(mods, "u1", title="x")
    tid = item["todoId"]
    r = mods["get_todo"].handler(event("u1", path=tid), None)
    assert r["statusCode"] == 200 and json.loads(r["body"]) == item
    for name, body in [("get_todo", None), ("update_todo", '{"title":"y"}'), ("delete_todo", None)]:
        r = mods[name].handler(event("u2", body=body, path=tid), None)
        assert r["statusCode"] == 404
        assert json.loads(r["body"]) == {"message": "Todo not found"}
    r = mods["update_todo"].handler(event("u1", body='{"status":"DONE"}', path=tid), None)
    assert r["statusCode"] == 200 and json.loads(r["body"])["status"] == "DONE"
    r = mods["delete_todo"].handler(event("u1", path=tid), None)
    assert r["statusCode"] == 204 and r["body"] == ""
    assert mods["delete_todo"].handler(event("u1", path=tid), None)["statusCode"] == 404


@pytest.mark.parametrize("body", ["not json", "[1]", None, '{"title":""}'])
def test_create_bad_body(h, body):
    mods, _ = h
    r = mods["create_todo"].handler(event("u1", body), None)
    assert r["statusCode"] == 400
    assert "message" in json.loads(r["body"])


def test_update_empty_body_400(h):
    mods, _ = h
    item = create(mods, "u1", title="x")
    r = mods["update_todo"].handler(event("u1", "{}", item["todoId"]), None)
    assert r["statusCode"] == 400


def test_list_activity_newest_first(h):
    mods, (_, activity) = h
    for ts, eid, action in [("2026-01-01T00:00:00+00:00", "a", "CREATED"),
                            ("2026-01-03T00:00:00+00:00", "c", "DELETED"),
                            ("2026-01-02T00:00:00+00:00", "b", "UPDATED")]:
        activity.put_item(Item={"userId": "u1", "sk": f"{ts}#{eid}", "action": action,
                                "todoId": "t", "title": "T", "ttl": 1900000000})
    activity.put_item(Item={"userId": "u2", "sk": "2026-01-04T00:00:00+00:00#z", "action": "CREATED"})
    r = mods["list_activity"].handler(event("u1"), None)
    assert r["statusCode"] == 200
    items = json.loads(r["body"])["items"]
    assert [i["action"] for i in items] == ["DELETED", "UPDATED", "CREATED"]
    assert all("userId" not in i and "ttl" not in i for i in items)
