import pytest

from todo_app.models import (
    ValidationError,
    parse_create,
    parse_update,
    status_due,
    to_public,
)


def test_parse_create_defaults():
    assert parse_create({"title": "  Buy milk "}) == {
        "title": "Buy milk",
        "description": "",
        "status": "OPEN",
        "dueDate": None,
    }


@pytest.mark.parametrize(
    "body",
    [
        {},
        {"title": ""},
        {"title": "   "},
        {"title": "x" * 201},
        {"title": "a", "description": "d" * 2001},
        {"title": "a", "status": "DOING"},
        {"title": "a", "dueDate": "2026-02-30"},
        {"title": "a", "dueDate": "30-10-2026"},
        {"title": "a", "dueDate": ""},
        {"title": "a", "dueDate": 123},
        {"title": "a", "owner": "x"},
    ],
)
def test_parse_create_rejects(body):
    with pytest.raises(ValidationError):
        parse_create(body)


def test_parse_create_accepts_limits():
    out = parse_create({"title": "x" * 200, "description": "d" * 2000,
                        "status": "DONE", "dueDate": "2026-11-01"})
    assert out["status"] == "DONE" and out["dueDate"] == "2026-11-01"


def test_parse_update():
    with pytest.raises(ValidationError):
        parse_update({})
    assert parse_update({"status": "DONE"}) == {"status": "DONE"}
    assert parse_update({"dueDate": None}) == {"dueDate": None}
    with pytest.raises(ValidationError):
        parse_update({"userId": "x"})


def test_status_due():
    assert status_due("OPEN", None) == "OPEN#9999-12-31"
    assert status_due("DONE", "2026-11-01") == "DONE#2026-11-01"


def test_to_public():
    item = {"userId": "u", "statusDue": "OPEN#9999-12-31", "todoId": "t",
            "title": "a", "description": "", "status": "OPEN",
            "createdAt": "c", "updatedAt": "u"}
    out = to_public(item)
    assert out == {"todoId": "t", "title": "a", "description": "",
                   "status": "OPEN", "dueDate": None,
                   "createdAt": "c", "updatedAt": "u"}
