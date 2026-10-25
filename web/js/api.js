// Talking to the pantryrun server (api/service.py).
import { identity } from "./identity.js";

// GET, or POST when there's a body. Throws when the answer isn't OK.
export async function api(path, body) {
  const res = await fetch(path, body ? { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) } : {});
  if (!res.ok) throw new Error(String(res.status));
  return res.json();
}

// Record what someone did, to learn what works. Never gets in the way of the page.
// The name only lets the server tell the founder's own use apart (core/events.py); it isn't stored.
export const logEvent = (type, data) =>
  api("/events", { type, data, user_id: identity.personId, session_id: identity.sessionId, name: identity.name }).catch(() => {});
