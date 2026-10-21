// Module-level cache-buster: bumps after every successful write so list GETs
// bypass any CDN/browser cache and read-your-writes holds.
let version = Date.now();

export function createApi(getToken, base = "/api") {
  async function request(method, path, { query = "", body } = {}) {
    const headers = { Authorization: getToken() }; // raw ID token, no "Bearer"
    if (body !== undefined) headers["Content-Type"] = "application/json";
    const res = await fetch(`${base}${path}${query}`, {
      method,
      headers,
      body: body !== undefined ? JSON.stringify(body) : undefined,
    });
    if (!res.ok) {
      let message = `Request failed (${res.status})`;
      try {
        const data = await res.json();
        if (data && data.message) message = data.message;
      } catch {
        /* non-JSON error body */
      }
      throw new Error(message);
    }
    if (method !== "GET") version += 1;
    return res.status === 204 ? null : res.json();
  }

  return {
    listTodos: (status) =>
      request("GET", "/todos", {
        query: `?v=${version}${status ? `&status=${encodeURIComponent(status)}` : ""}`,
      }),
    createTodo: (fields) => request("POST", "/todos", { body: fields }),
    updateTodo: (id, fields) =>
      request("PUT", `/todos/${encodeURIComponent(id)}`, { body: fields }),
    deleteTodo: (id) => request("DELETE", `/todos/${encodeURIComponent(id)}`),
    listActivity: () => request("GET", "/activity", { query: `?v=${version}` }),
  };
}
