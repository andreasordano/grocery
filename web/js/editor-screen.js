// Writing your own dinner: a name, what you buy for it (with amounts if you like), for how many people.
// Saved dinners appear under "Mine" and are priced like any other. "Make it yours" starts from a copy of
// any other dinner (a classic, a NutriData dish, one sent by link).
import { $, pick } from "./dom.js";
import { esc } from "./format.js";
import { state } from "./state.js";
import { storage } from "./storage.js";
import { identity } from "./identity.js";
import { render } from "./screens.js";
import { bindAdd, itemButton, itemClick } from "./items.js";
import { idle } from "./receipt.js";
import { add, unpick } from "./dinners.js";
import { api, logEvent } from "./api.js";

export function open() {
  draw();
  idle("Your dinner", "Save it, then pick it to find the store.");
}

export function draw() {
  const d = state.editing;
  pick.innerHTML = `
    <div class="editor">
      <h1>${d.id ? "Edit dinner" : d.from ? "Make it yours" : "New dinner"}</h1>
      ${d.from ? `<p class="fine copy-note">A copy: change what you like and save it. The original stays as it is.</p>` : ""}
      <form class="from-link" id="fromLink" autocomplete="off"${d.from ? " hidden" : ""}>
        <label for="dlinkImport">${d.id ? "Fill it in again from a recipe page" : "Start from a recipe you found online"}</label>
        <div class="field">
          <input id="dlinkImport" type="text" inputmode="url" autocapitalize="off" spellcheck="false" placeholder="Paste a link, e.g. rimi.ee/retseptid/…" enterkeyhint="go">
          <button class="btn quiet" type="submit" id="readLink">Read it</button>
        </div>
        <p class="fine" id="linkNote" role="status"></p>
      </form>
      ${d.image ? `<div class="d-photo"><img src="${esc(d.image)}" alt="" referrerpolicy="no-referrer">
        <button type="button" class="link" id="dropPhoto">Remove photo</button></div>` : ""}
      <div class="sub">For
        <span class="stepper" role="group" aria-label="Number of people the amounts are for">
          <button type="button" data-dstep="-1" aria-label="Fewer people">−</button>
          <output id="dservings">${d.servings}</output>
          <button type="button" data-dstep="1" aria-label="More people">+</button>
        </span> people</div>
      <label for="dname">Name</label>
      <input id="dname" class="name" maxlength="80" value="${esc(d.name)}" placeholder="Pühapäeva pasta" autocomplete="off">
      <h2>What you buy for it</h2>
      <p class="fine">Amounts are for ${d.servings} ${d.servings === 1 ? "person" : "people"} and scale with how many you cook for.</p>
      <form class="field" id="add" autocomplete="off">
        <input id="item" placeholder="hakkliha 500g, sibul, 2 purustatud tomatid" aria-label="Add things to buy" enterkeyhint="done">
        <button class="btn quiet" type="submit">Add</button>
      </form>
      <ul class="items">${d.items.length ? d.items.map((it, i) => `
        <li>${itemButton(it, i)}<button type="button" data-remove="${i}" aria-label="Remove ${esc(it)}">×</button></li>`).join("")
        : `<li class="none">Nothing to buy yet.</li>`}
      </ul>
      <h2><label for="dmethod">How you cook it</label></h2>
      <p class="fine">Optional. It shows on the recipe card next to the shopping list, and goes along when you send the dinner.</p>
      <textarea id="dmethod" class="method" rows="5" maxlength="4000" placeholder="1. Fry the mince with the onion.&#10;2. Add the sour cream and simmer for 10 minutes.">${esc(d.method)}</textarea>
      <h2><label for="dlink">Recipe link</label></h2>
      <p class="fine">Optional. A page with the full recipe.</p>
      <input id="dlink" class="name" type="url" inputmode="url" maxlength="500" value="${esc(d.link)}" placeholder="https://nami-nami.ee/retseptid/…" autocomplete="off">
      <div class="actions">
        <button class="btn dark" id="saveDinner" type="button">Save dinner</button>
        <button class="btn quiet" id="cancelDinner" type="button">Cancel</button>
        ${d.id ? `<button class="link" id="deleteDinner" type="button">Delete</button>` : ""}
      </div>
      <p class="error" id="dinnerError" role="alert"></p>
    </div>`;
  $("#dname").addEventListener("input", e => { d.name = e.target.value; });
  $("#dmethod").addEventListener("input", e => { d.method = e.target.value; });
  $("#dlink").addEventListener("input", e => { d.link = e.target.value; });
  $("#fromLink").onsubmit = e => { e.preventDefault(); readLink(); };
  bindAdd(d.items, draw);
  pick.onclick = onClick;
}

// "Make it yours": a copy of any dinner, to change and save as a new one of your own.
export async function copyDinner(id) {
  try {
    const c = await api(`/recipes/${encodeURIComponent(id)}/copy?user_id=${encodeURIComponent(identity.personId)}`);
    state.editing = { id: null, from: c.from, name: c.name, servings: c.servings, items: c.items, method: c.method,
                      link: c.link, image: c.image };
    logEvent("dinner_copy", { from: id });
    render();
    $("#item").focus();
  } catch {
    idle("Couldn't copy that dinner", "Check your connection, then try again.");
  }
}

// Open the editor for one of your dinners, or for a new one (id null), ready for a recipe link.
export function editDinner(id, { fromLink = false } = {}) {
  const m = id && state.mine.find(x => x.id === id);
  state.editing = m ? { id: m.id, name: m.name, servings: m.servings, items: [...m.items], method: m.method || "", link: m.link || "", image: m.image || "" }
                    : { id: null, name: "", servings: state.servings, items: [], method: "", link: "", image: "" };
  render();
  $(m ? "#item" : fromLink ? "#dlinkImport" : "#dname").focus();
}

function onClick(e) {
  const step = e.target.closest("[data-dstep]");
  if (step) {
    state.editing.servings = Math.min(12, Math.max(1, state.editing.servings + +step.dataset.dstep));
    draw();
    return;
  }
  if (itemClick(e, state.editing.items, draw)) return;
  if (e.target.closest("#saveDinner")) { saveDinner(); return; }
  if (e.target.closest("#dropPhoto")) { state.editing.image = ""; draw(); return; }
  if (e.target.closest("#cancelDinner")) { state.editing = null; render(); return; }
  if (e.target.closest("#deleteDinner")) deleteDinner();
}

// A recipe page read into the dinner: its name, servings, what to buy, photo and link (core/recipe_import.py).
// What's already typed stays; the page's items are added after it.
async function readLink() {
  const d = state.editing, url = $("#dlinkImport").value.trim(), note = $("#linkNote");
  if (!url) return;
  note.textContent = "Reading the page…";
  $("#readLink").disabled = true;
  try {
    const res = await fetch("/recipe-import", { method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ url, user_id: identity.personId }) });
    const found = await res.json();
    if (!res.ok) { note.textContent = found.detail || "Couldn't read that page."; $("#readLink").disabled = false; return; }
    if (!d.name.trim()) d.name = found.name;
    d.servings = found.servings;
    d.items = [...new Set([...d.items, ...found.items])];
    d.link = found.link;
    d.image = found.image || d.image;
    const site = new URL(found.link).hostname.replace(/^www\./, "");
    draw();
    $("#linkNote").textContent = found.items.length
      ? `Found ${found.items.length} things to buy on ${site}. Check them, then save. The method stays on ${site}: the dinner links to it.`
      : `${site} doesn't list its ingredients in a way pantryrun can read. Type what you buy for it below.`;
  } catch {
    note.textContent = "Couldn't reach pantryrun. Check your connection, then try again.";
    $("#readLink").disabled = false;
  }
}

async function saveDinner() {
  const d = state.editing;
  const body = { user_id: identity.personId, name: d.name, servings: d.servings, items: d.items, method: d.method, link: d.link,
                 image: d.image, from_dinner: d.from ?? null };
  try {
    const res = await fetch(d.id ? `/my-dinners/${encodeURIComponent(d.id)}` : "/my-dinners", {
      method: d.id ? "PUT" : "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) });
    const saved = await res.json();
    if (!res.ok) { $("#dinnerError").textContent = saved.detail || "Couldn't save the dinner. Try again."; return; }
    state.mine = [...state.mine.filter(x => x.id !== saved.id), saved].sort((a, b) => a.name.localeCompare(b.name));
    state.editing = null;
    state.category = "mine"; storage.set("pantryrun.category", "mine"); state.shown = [];
    add(saved.id);  // picked straight away, so it's priced
    render();
  } catch {
    $("#dinnerError").textContent = "Couldn't reach pantryrun. Check your connection, then try again.";
  }
}

async function deleteDinner() {
  const d = state.editing;
  if (!confirm(`Delete "${d.name}"?`)) return;
  const res = await fetch(`/my-dinners/${encodeURIComponent(d.id)}?user_id=${encodeURIComponent(identity.personId)}`, { method: "DELETE" });
  if (!res.ok && res.status !== 404) { $("#dinnerError").textContent = "Couldn't delete the dinner. Try again."; return; }
  state.mine = state.mine.filter(x => x.id !== d.id);
  unpick(d.id);
  state.editing = null; state.shown = [];
  render();
}
