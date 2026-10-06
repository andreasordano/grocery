// Writing your own dinner: a name, what you buy for it (with amounts if you like), for how many people.
// Saved dinners appear under "Mine" and are priced like any other.
import { $, pick } from "./dom.js";
import { esc } from "./format.js";
import { state } from "./state.js";
import { storage } from "./storage.js";
import { identity } from "./identity.js";
import { render } from "./screens.js";
import { bindAdd, itemButton, itemClick } from "./items.js";
import { idle } from "./receipt.js";

export function open() {
  draw();
  idle("Your dinner", "Save it, then pick it to find the store.");
}

export function draw() {
  const d = state.editing;
  pick.innerHTML = `
    <div class="editor">
      <h1>${d.id ? "Edit dinner" : "New dinner"}</h1>
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
      <div class="actions">
        <button class="btn dark" id="saveDinner" type="button">Save dinner</button>
        <button class="btn quiet" id="cancelDinner" type="button">Cancel</button>
        ${d.id ? `<button class="link" id="deleteDinner" type="button">Delete</button>` : ""}
      </div>
      <p class="error" id="dinnerError" role="alert"></p>
    </div>`;
  $("#dname").addEventListener("input", e => { d.name = e.target.value; });
  bindAdd(d.items, draw);
  pick.onclick = onClick;
}

// Open the editor for one of your dinners, or for a new one (id null).
export function editDinner(id) {
  const m = id && state.mine.find(x => x.id === id);
  state.editing = m ? { id: m.id, name: m.name, servings: m.servings, items: [...m.items] }
                    : { id: null, name: "", servings: state.servings, items: [] };
  render();
  $(m ? "#item" : "#dname").focus();
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
  if (e.target.closest("#cancelDinner")) { state.editing = null; render(); return; }
  if (e.target.closest("#deleteDinner")) deleteDinner();
}

async function saveDinner() {
  const d = state.editing;
  const body = { user_id: identity.userId, name: d.name, servings: d.servings, items: d.items };
  try {
    const res = await fetch(d.id ? `/my-dinners/${encodeURIComponent(d.id)}` : "/my-dinners", {
      method: d.id ? "PUT" : "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) });
    const saved = await res.json();
    if (!res.ok) { $("#dinnerError").textContent = saved.detail || "Couldn't save the dinner. Try again."; return; }
    state.mine = [...state.mine.filter(x => x.id !== saved.id), saved].sort((a, b) => a.name.localeCompare(b.name));
    state.editing = null;
    state.category = "mine"; storage.set("pantryrun.category", "mine"); state.shown = [];
    state.recipeId = saved.id;  // picked straight away, so it's priced
    render();
  } catch {
    $("#dinnerError").textContent = "Couldn't reach pantryrun. Check your connection, then try again.";
  }
}

async function deleteDinner() {
  const d = state.editing;
  if (!confirm(`Delete "${d.name}"?`)) return;
  const res = await fetch(`/my-dinners/${encodeURIComponent(d.id)}?user_id=${encodeURIComponent(identity.userId)}`, { method: "DELETE" });
  if (!res.ok && res.status !== 404) { $("#dinnerError").textContent = "Couldn't delete the dinner. Try again."; return; }
  state.mine = state.mine.filter(x => x.id !== d.id);
  if (state.recipeId === d.id) state.recipeId = null;
  state.editing = null; state.shown = [];
  render();
}
