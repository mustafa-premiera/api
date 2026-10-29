import { test } from "node:test";
import assert from "node:assert/strict";
import { withAdded, withReplaced, withUpdated, without } from "./todoList.js";

const a = { todoId: "a", title: "A", status: "OPEN" };
const b = { todoId: "b", title: "B", status: "DONE" };

test("withAdded puts the new item first when it matches the filter", () => {
  const t = { todoId: "tmp-1", title: "New", status: "OPEN" };
  assert.deepEqual(withAdded([a, b], t, ""), [t, a, b]);
  assert.deepEqual(withAdded([a], t, "OPEN"), [t, a]);
});

test("withAdded leaves the list alone when the item doesn't match the filter", () => {
  const t = { todoId: "tmp-1", title: "New", status: "OPEN" };
  assert.deepEqual(withAdded([b], t, "DONE"), [b]);
});

test("withReplaced swaps the temporary item for the server's copy in place", () => {
  const tmp = { todoId: "tmp-1", title: "New", status: "OPEN", pending: true };
  const saved = { todoId: "x", title: "New", status: "OPEN", createdAt: "2026-10-29T00:00:00+00:00" };
  assert.deepEqual(withReplaced([a, tmp, b], "tmp-1", saved, ""), [a, saved, b]);
});

test("withReplaced drops the temporary item if the server's copy no longer matches the filter", () => {
  const tmp = { todoId: "tmp-1", title: "New", status: "OPEN" };
  const saved = { todoId: "x", title: "New", status: "DONE" };
  assert.deepEqual(withReplaced([tmp, a], "tmp-1", saved, "OPEN"), [a]);
});

test("withUpdated applies changes and keeps the item when it still matches", () => {
  assert.deepEqual(withUpdated([a, b], "a", { title: "A2" }, ""), [{ ...a, title: "A2" }, b]);
  assert.deepEqual(withUpdated([a, b], "a", { status: "DONE" }, ""), [{ ...a, status: "DONE" }, b]);
});

test("withUpdated removes the item when the change takes it out of the filter", () => {
  assert.deepEqual(withUpdated([a], "a", { status: "DONE" }, "OPEN"), []);
});

test("without removes only the given item", () => {
  assert.deepEqual(without([a, b], "a"), [b]);
  assert.deepEqual(without([a, b], "missing"), [a, b]);
});
