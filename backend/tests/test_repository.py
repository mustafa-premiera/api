import pytest

from todo_app.repository import TodoRepository


@pytest.fixture
def repo(tables):
    return TodoRepository(tables[0])


def fields(title="t", status="OPEN", due=None):
    return {"title": title, "description": "", "status": status, "dueDate": due}


def test_create_get_roundtrip(repo):
    created = repo.create("u1", fields("a", due="2026-11-01"))
    assert created["statusDue"] == "OPEN#2026-11-01"
    assert repo.get("u1", created["todoId"]) == created
    assert repo.get("u2", created["todoId"]) is None


def test_create_without_due_omits_attribute(repo):
    created = repo.create("u1", fields())
    assert "dueDate" not in repo.get("u1", created["todoId"])


def test_list_isolated_by_user(repo):
    a = repo.create("u1", fields("a"))
    repo.create("u2", fields("b"))
    assert [i["todoId"] for i in repo.list("u1")] == [a["todoId"]]


def test_list_all_newest_first(repo, monkeypatch):
    from todo_app import repository

    ids = []
    for n, ts in enumerate(["2026-10-01T00:00:00+00:00", "2026-10-03T00:00:00+00:00", "2026-10-02T00:00:00+00:00"]):
        monkeypatch.setattr(repository, "_now", lambda ts=ts: ts)
        ids.append(repo.create("u1", fields(f"t{n}"))["todoId"])
    assert [i["todoId"] for i in repo.list("u1")] == [ids[1], ids[2], ids[0]]


def test_list_by_status_ordered_by_due(repo):
    late = repo.create("u1", fields("late", due="2026-12-01"))
    none = repo.create("u1", fields("none"))
    early = repo.create("u1", fields("early", due="2026-11-01"))
    repo.create("u1", fields("done", status="DONE", due="2026-10-01"))
    repo.create("u2", fields("other", due="2026-01-01"))
    got = repo.list("u1", "OPEN")
    assert [i["todoId"] for i in got] == [early["todoId"], late["todoId"], none["todoId"]]


def test_update_other_users_item_returns_none(repo):
    t = repo.create("u2", fields("mine"))
    assert repo.update("u1", t["todoId"], {"title": "hacked"}) is None
    assert repo.get("u2", t["todoId"])["title"] == "mine"
    assert repo.get("u1", t["todoId"]) is None


def test_update_changes_fields_and_status_due(repo):
    t = repo.create("u1", fields("a", due="2026-11-01"))
    out = repo.update("u1", t["todoId"], {"status": "DONE", "title": "b"})
    assert out["title"] == "b" and out["status"] == "DONE"
    assert out["statusDue"] == "DONE#2026-11-01"
    assert out["dueDate"] == "2026-11-01"


def test_update_clear_due_date(repo):
    t = repo.create("u1", fields("a", due="2026-11-01"))
    out = repo.update("u1", t["todoId"], {"dueDate": None})
    assert "dueDate" not in out
    assert out["statusDue"] == "OPEN#9999-12-31"
    assert "dueDate" not in repo.get("u1", t["todoId"])


def test_update_set_due_date(repo):
    t = repo.create("u1", fields("a"))
    out = repo.update("u1", t["todoId"], {"dueDate": "2026-12-25"})
    assert out["dueDate"] == "2026-12-25"
    assert out["statusDue"] == "OPEN#2026-12-25"


def test_delete(repo):
    assert repo.delete("u1", "missing") is False
    t = repo.create("u1", fields())
    assert repo.delete("u2", t["todoId"]) is False
    assert repo.delete("u1", t["todoId"]) is True
    assert repo.get("u1", t["todoId"]) is None
