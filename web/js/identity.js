// Who is using pantryrun. Each browser gets a random person id on its first visit; a tester link (?u=)
// sets the id instead, and someone who typed a name before ids existed keeps that name as their id,
// so their saved dinners stay theirs. There are no passwords.
// The name is optional and only asked for when someone saves their first dinner.
import { $ } from "./dom.js";
import { storage } from "./storage.js";

const link = new URLSearchParams(location.search).get("u");
const known = storage.get("pantryrun.person", null) || storage.get("pantryrun.name", null);

export const identity = {
  personId: link || known || crypto.randomUUID(),
  fromTesterLink: !!link,
  firstVisit: !link && !known,
  name: storage.get("pantryrun.name", null),  // null: never asked; "": skipped
  sessionId: (() => {
    try {
      let id = sessionStorage.getItem("sid");
      if (!id) { id = crypto.randomUUID(); sessionStorage.setItem("sid", id); }
      return id;
    } catch { return crypto.randomUUID(); }
  })(),
};
storage.set("pantryrun.person", identity.personId);

// Ask for a name once. Resolves with the name typed, or null when it was skipped or asked before.
export function askName() {
  if (identity.name !== null) return Promise.resolve(null);
  const hello = $("#hello"), input = $("#helloName");
  return new Promise(resolve => {
    hello.returnValue = "";
    hello.onclose = () => {
      const name = hello.returnValue === "save" ? input.value.trim().replace(/\s+/g, " ") : "";
      identity.name = name;
      storage.set("pantryrun.name", name);
      resolve(name || null);
    };
    input.oninput = () => input.setCustomValidity(input.value.trim() ? "" : "Please type your name, or skip.");
    hello.showModal();
  });
}
