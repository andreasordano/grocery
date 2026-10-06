// What the browser remembers between visits: the name, product preferences, the last kind of dinner.
// Keys were "groceries.*" before the rename to pantryrun; those are still read so testers keep their name and prefs.

export const storage = {
  get(key, fallback) {
    try { return JSON.parse(localStorage.getItem(key) ?? localStorage.getItem(key.replace(/^pantryrun\./, "groceries."))) ?? fallback; }
    catch { return fallback; }
  },
  set(key, value) {
    try { localStorage.setItem(key, JSON.stringify(value)); } catch {}
  },
};
