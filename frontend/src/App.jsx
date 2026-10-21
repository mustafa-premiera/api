import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useAuth } from "react-oidc-context";
import { createApi } from "./api.js";

const FILTERS = [
  ["", "All"],
  ["OPEN", "Open"],
  ["DONE", "Done"],
];

export default function App({ config }) {
  const auth = useAuth();

  if (auth.isLoading) return <main className="wrap"><p>Loading…</p></main>;

  if (auth.error) {
    return (
      <main className="wrap">
        <h1>Manara To-Do</h1>
        <div className="banner" role="alert">{auth.error.message}</div>
        <button onClick={() => auth.signinRedirect()}>Try again</button>
      </main>
    );
  }

  if (!auth.isAuthenticated) {
    return (
      <main className="wrap">
        <h1>Manara To-Do</h1>
        <p className="intro">
          A demo for Project 3 of Manara's "Becoming a Solutions Architect": a serverless
          to-do API built with Cognito, API Gateway, Lambda, DynamoDB, WAF, CloudFront and
          X-Ray. Sign in or create an account to try it.
        </p>
        <button onClick={() => auth.signinRedirect()}>Sign in / Sign up</button>
      </main>
    );
  }

  return <Todos auth={auth} config={config} />;
}

function Todos({ auth, config }) {
  const tokenRef = useRef(auth.user.id_token);
  tokenRef.current = auth.user.id_token;
  const api = useMemo(() => createApi(() => tokenRef.current, config.apiBase || "/api"), [config.apiBase]);

  const [todos, setTodos] = useState([]);
  const [activity, setActivity] = useState([]);
  const [filter, setFilter] = useState("");
  const [error, setError] = useState(null);
  const [title, setTitle] = useState("");
  const [dueDate, setDueDate] = useState("");
  const [editing, setEditing] = useState(null); // {id, text}
  const timer = useRef(null);

  const loadTodos = useCallback(
    () => api.listTodos(filter || undefined).then((d) => setTodos(d.items || [])).catch((e) => setError(e.message)),
    [api, filter]
  );
  const loadActivity = useCallback(
    () => api.listActivity().then((d) => setActivity(d.items || [])).catch((e) => setError(e.message)),
    [api]
  );

  useEffect(() => { loadTodos(); }, [loadTodos]);
  useEffect(() => { loadActivity(); return () => clearTimeout(timer.current); }, [loadActivity]);

  // Activity is written asynchronously via DynamoDB Streams, so reload after a delay.
  const scheduleActivity = () => {
    clearTimeout(timer.current);
    timer.current = setTimeout(loadActivity, 3000);
  };

  const write = async (fn) => {
    try {
      await fn();
      await loadTodos();
      scheduleActivity();
    } catch (e) {
      setError(e.message);
    }
  };

  const add = (e) => {
    e.preventDefault();
    const t = title.trim();
    if (!t) return;
    const fields = { title: t };
    if (dueDate) fields.dueDate = dueDate;
    write(async () => {
      await api.createTodo(fields);
      setTitle("");
      setDueDate("");
    });
  };

  const saveEdit = () => {
    const { id, text } = editing;
    setEditing(null);
    const t = text.trim();
    const current = todos.find((x) => x.todoId === id);
    if (!t || !current || t === current.title) return;
    write(() => api.updateTodo(id, { title: t }));
  };

  const signOut = async () => {
    await auth.removeUser();
    const q = new URLSearchParams({ client_id: config.clientId, logout_uri: config.redirectUri });
    window.location.href = `${config.cognitoDomain}/logout?${q}`;
  };

  return (
    <main className="wrap">
      <header className="top">
        <h1>Manara To-Do</h1>
        <div className="who">
          <span>{auth.user.profile.email}</span>
          <button className="secondary" onClick={signOut}>Sign out</button>
        </div>
      </header>

      {error && (
        <div className="banner" role="alert">
          <span>{error}</span>
          <button className="link" aria-label="Dismiss error" onClick={() => setError(null)}>×</button>
        </div>
      )}

      <form className="add" onSubmit={add}>
        <input value={title} onChange={(e) => setTitle(e.target.value)} placeholder="New to-do" aria-label="Title" maxLength={200} />
        <input type="date" value={dueDate} onChange={(e) => setDueDate(e.target.value)} aria-label="Due date (optional)" />
        <button type="submit">Add</button>
      </form>

      <div className="filters" role="group" aria-label="Filter">
        {FILTERS.map(([v, label]) => (
          <button key={label} className={filter === v ? "active" : "secondary"} onClick={() => setFilter(v)}>{label}</button>
        ))}
      </div>

      <ul className="todos">
        {todos.length === 0 && <li className="empty">Nothing here yet.</li>}
        {todos.map((t) => (
          <li key={t.todoId} className={t.status === "DONE" ? "done" : ""}>
            <input
              type="checkbox"
              checked={t.status === "DONE"}
              aria-label={`Mark "${t.title}" done`}
              onChange={() => write(() => api.updateTodo(t.todoId, { status: t.status === "DONE" ? "OPEN" : "DONE" }))}
            />
            {editing && editing.id === t.todoId ? (
              <input
                className="edit"
                autoFocus
                value={editing.text}
                onChange={(e) => setEditing({ id: t.todoId, text: e.target.value })}
                onBlur={saveEdit}
                onKeyDown={(e) => {
                  if (e.key === "Enter") e.currentTarget.blur();
                  if (e.key === "Escape") setEditing(null);
                }}
              />
            ) : (
              <span className="title" title="Click to edit" onClick={() => setEditing({ id: t.todoId, text: t.title })}>
                {t.title}
              </span>
            )}
            {t.dueDate && <span className="due">{t.dueDate}</span>}
            <button className="danger" aria-label={`Delete "${t.title}"`} onClick={() => write(() => api.deleteTodo(t.todoId))}>Delete</button>
          </li>
        ))}
      </ul>

      <section className="activity">
        <h2>Recent activity (DynamoDB Streams)</h2>
        <ul>
          {activity.length === 0 && <li className="empty">No activity yet.</li>}
          {activity.map((a) => (
            <li key={a.sk}><strong>{a.action}</strong> {a.title}</li>
          ))}
        </ul>
      </section>
    </main>
  );
}
