// Pure list updates for optimistic UI: the list changes as soon as the user acts,
// and the server's reply (or a reload after an error) settles it.

const matches = (todo, filter) => !filter || todo.status === filter;

// New items go first, matching the server's newest-first order for "All".
export const withAdded = (todos, todo, filter) => (matches(todo, filter) ? [todo, ...todos] : todos);

export const withReplaced = (todos, id, saved, filter) =>
  matches(saved, filter) ? todos.map((t) => (t.todoId === id ? saved : t)) : without(todos, id);

export const withUpdated = (todos, id, changes, filter) =>
  todos
    .map((t) => (t.todoId === id ? { ...t, ...changes } : t))
    .filter((t) => t.todoId !== id || matches(t, filter));

export const without = (todos, id) => todos.filter((t) => t.todoId !== id);
