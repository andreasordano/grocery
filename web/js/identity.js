// Who is using pantryrun. Each browser gets a random person id on its first visit; a tester link (?u=)
// sets the id instead, and someone who typed a name before ids existed keeps that name as their id,
// so their saved dinners stay theirs. There are no passwords.
// The name is asked for on the first visit and can't be skipped: it tells us who did what. People who
// came with a tester link aren't asked; the link says who they are.
import { $ } from "./dom.js";
import { chains, esc } from "./format.js";
import { storage } from "./storage.js";

const link = new URLSearchParams(location.search).get("u");
if (link) storage.set("pantryrun.tester", true);
const known = storage.get("pantryrun.person", null) || storage.get("pantryrun.name", null);

export const identity = {
  personId: link || known || crypto.randomUUID(),
  fromTesterLink: !!link,
  tester: !!link || storage.get("pantryrun.tester", false),  // ever came with a tester link
  firstVisit: !link && !known,
  name: storage.get("pantryrun.name", null),  // null: never asked; "": skipped (when it could be)
  usualStore: storage.get("pantryrun.usualStore", undefined),  // selver/rimi/maxima/other, "skip", or undefined: never asked
  sessionId: (() => {
    try {
      let id = sessionStorage.getItem("sid");
      if (!id) { id = crypto.randomUUID(); sessionStorage.setItem("sid", id); }
      return id;
    } catch { return crypto.randomUUID(); }
  })(),
};
storage.set("pantryrun.person", identity.personId);

// Ask for the name, once. Resolves with the name typed, or null when it's known (or a tester link).
// The dialog can't be closed without a name.
export function askName() {
  if (identity.name || identity.tester) return Promise.resolve(null);
  const hello = $("#hello"), input = $("#helloName");
  return new Promise(resolve => {
    hello.oncancel = e => e.preventDefault();  // Escape
    hello.onclose = () => {
      const name = input.value.trim().replace(/\s+/g, " ");
      if (!name) { hello.showModal(); return; }  // a second Escape still closes it in Chrome
      identity.name = name;
      storage.set("pantryrun.name", name);
      resolve(name);
    };
    input.oninput = () => input.setCustomValidity(input.value.trim() ? "" : "Please type your name.");
    hello.showModal();
  });
}

// Where someone usually shops (a chain from stores_config.py, or other), asked once with one tap. Resolves with
// the answer (null for Skip), or undefined when it was asked before.
export function askUsualStore() {
  if (identity.usualStore !== undefined) return Promise.resolve(undefined);
  const usual = $("#usual"), choices = [...Object.keys(chains()), "other"];
  $("#usualChoices").innerHTML = choices.map(c => `<button type="submit" value="${esc(c)}">${esc(chains()[c] ?? "Other")}</button>`).join("");
  return new Promise(resolve => {
    usual.returnValue = "";
    usual.onclose = () => {
      const store = choices.includes(usual.returnValue) ? usual.returnValue : null;
      setUsualStore(store ?? "skip");  // kept as "skip": a stored null reads back as never asked
      resolve(store);
    };
    usual.showModal();
  });
}

export function setUsualStore(store) {
  identity.usualStore = store;
  storage.set("pantryrun.usualStore", store);
}
