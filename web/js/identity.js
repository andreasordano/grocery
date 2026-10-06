// Who is using pantryrun: ?u= in the link wins, otherwise the name asked for on the first visit.
// There are no passwords; the name keeps someone's own dinners and tells us who tried it.
import { $ } from "./dom.js";
import { storage } from "./storage.js";

export const identity = {
  userId: new URLSearchParams(location.search).get("u") || storage.get("pantryrun.name", null),
  sessionId: (() => {
    try {
      let id = sessionStorage.getItem("sid");
      if (!id) { id = crypto.randomUUID(); sessionStorage.setItem("sid", id); }
      return id;
    } catch { return crypto.randomUUID(); }
  })(),
};

// The first-visit dialog. A name is required, so it can't be closed without one. Resolves once it's typed.
export function askName() {
  const hello = $("#hello"), input = $("#helloName");
  return new Promise(resolve => {
    hello.oncancel = e => e.preventDefault();
    hello.onclose = () => { if (!identity.userId) hello.showModal(); };  // a second Escape still closes it in Chrome
    $("#helloForm").onsubmit = () => {
      identity.userId = input.value.trim().replace(/\s+/g, " ");
      storage.set("pantryrun.name", identity.userId);
      resolve();
    };
    input.oninput = () => input.setCustomValidity(input.value.trim() ? "" : "Please type your name.");
    hello.showModal();
  });
}
