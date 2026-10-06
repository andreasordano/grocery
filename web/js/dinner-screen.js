// The Dinner screen: how many people, kinds of dinner, a handful of dinners to pick from,
// anything else for the trip, and a dinner someone sent by link.
import { $, pick } from "./dom.js";
import { esc } from "./format.js";
import { state } from "./state.js";
import { storage } from "./storage.js";
import { identity } from "./identity.js";
import { api, logEvent } from "./api.js";
import { shownDinners, shuffle } from "./dinners.js";
import { bindAdd, itemButton, itemClick } from "./items.js";
import { ask } from "./basket.js";
import { idle } from "./receipt.js";
import { editDinner } from "./editor-screen.js";

const pickADinner = () => idle("Pick a dinner", "Your store and shopping list print here.");

export function open() {
  draw();
  state.recipeId ? ask({ fresh: true }) : pickADinner();
}

export function draw() {
  const dinners = shownDinners();
  pick.innerHTML = `
    <h1>Dinner <span class="for">for <span class="stepper" role="group" aria-label="Number of people">
        <button type="button" data-step="-1" aria-label="Fewer people">−</button>
        <output id="servings">${state.servings}</output>
        <button type="button" data-step="1" aria-label="More people">+</button>
      </span></span> tonight</h1>
    ${state.shared ? `<div class="sent">
      <p><span class="what">A dinner sent to you</span><span class="name" lang="et">${esc(state.shared.name)}</span></p>
      <span class="btns">${state.shared.saved ? `<span class="fine">Saved to Mine</span>`
        : `<button type="button" class="btn quiet" id="saveShared">Save to my dinners</button>`}
        <button type="button" class="x" id="dropShared" aria-label="Close">×</button></span>
    </div>` : ""}
    <div class="chips cats" role="group" aria-label="Kind of dinner">${[
      { id: "ideas", name: "Ideas" }, { id: "classics", name: "Classics" }, { id: "mine", name: "Mine" }, ...state.categories,
    ].map(c => `<button type="button" data-cat="${esc(c.id)}" aria-pressed="${c.id === state.category}">${esc(c.name)}</button>`).join("")}</div>
    ${state.category === "mine" && !state.mine.length ? `<p class="empty">Write down a dinner you cook often. Type what you
      buy for it once, with amounts if you like, and pantryrun finds the store each time.</p>` : ""}
    <ul class="dishes">${dinners.map(r => `
      <li${r.id.startsWith("my-") ? ` class="mine"` : ""}><button type="button" class="dish" data-id="${esc(r.id)}" aria-pressed="${r.id === state.recipeId}">
        <span lang="et">${esc(r.name)}</span></button>${r.id.startsWith("my-")
        ? `<button type="button" class="link" data-edit-dinner="${esc(r.id)}" aria-label="Edit ${esc(r.name)}">Edit</button>` : ""}</li>`).join("")}
    </ul>
    <div class="more">${state.category === "mine" ? `<button type="button" class="btn quiet" id="newDinner">New dinner</button>`
      : state.category === "classics" ? ""
      : `<button type="button" class="link" id="shuffle">Show me others</button>`}
      ${dinners.some(r => r.id.startsWith("nd-")) ? `<span class="fine">Dishes from NutriData, Tervise Arengu Instituut</span>` : ""}</div>
    <div class="extras">${state.extrasOpen || state.extras.length ? `
      <h2>Anything else on the way?</h2>
      <form class="field" id="add" autocomplete="off">
        <input id="item" placeholder="kohv, leib, banaanid 1kg" aria-label="Add more items" enterkeyhint="done">
        <button class="btn quiet" type="submit">Add</button>
      </form>
      ${state.extras.length ? `<ul class="tags">${state.extras.map((it, i) => `
        <li>${itemButton(it, i)}<button type="button" data-remove="${i}" aria-label="Remove ${esc(it)}">×</button></li>`).join("")}</ul>` : ""}`
      : `<button type="button" class="open-extras" id="openExtras"><span aria-hidden="true">+</span>Anything else on the way?</button>`}
    </div>`;
  if (state.extrasOpen || state.extras.length) bindAdd(state.extras, extrasChanged);
  pick.onclick = onClick;
}

// After the extras change: redraw, and price the dinner again if one is picked.
function extrasChanged() {
  draw();
  if (state.recipeId) ask();
}

let stepTimer;

function onClick(e) {
  const dish = e.target.closest(".dish");
  if (dish) {
    state.recipeId = dish.dataset.id;
    pick.querySelectorAll(".dish").forEach(d => d.setAttribute("aria-pressed", d === dish));
    ask({ fresh: true });
    return;
  }
  const cat = e.target.closest("[data-cat]");
  if (cat) {
    state.category = cat.dataset.cat;
    storage.set("pantryrun.category", state.category);
    state.shown = [];
    draw();
    logEvent("dinner_category", { category: state.category });
    return;
  }
  if (e.target.closest("#shuffle")) {
    shuffle(state.shown);
    draw();
    logEvent("dinner_shuffle", { category: state.category });
    return;
  }
  const step = e.target.closest("[data-step]");
  if (step) {
    state.servings = Math.min(8, Math.max(1, state.servings + +step.dataset.step));
    $("#servings").textContent = state.servings;
    clearTimeout(stepTimer);
    if (state.recipeId) stepTimer = setTimeout(ask, 350);  // wait for the last tap
    return;
  }
  if (itemClick(e, state.extras, extrasChanged)) return;
  const editOwn = e.target.closest("[data-edit-dinner]");
  if (editOwn) { editDinner(editOwn.dataset.editDinner); return; }
  if (e.target.closest("#newDinner")) { editDinner(null); return; }
  if (e.target.closest("#openExtras")) { state.extrasOpen = true; draw(); $("#item").focus(); return; }
  if (e.target.closest("#saveShared")) { saveShared(); return; }
  if (e.target.closest("#dropShared")) dropShared();
}

async function saveShared() {
  const d = state.shared;
  try {
    const saved = await api("/my-dinners", { user_id: identity.userId, name: d.name, servings: d.servings, items: d.items, from_share: d.token });
    state.mine = [...state.mine, saved].sort((a, b) => a.name.localeCompare(b.name));
    d.saved = true;
    draw();
  } catch {
    $("#saveShared").textContent = "Couldn't save. Try again";
  }
}

// Close the sent dinner, and take it out of the address so a reload doesn't bring it back.
function dropShared() {
  if (state.recipeId === state.shared.id) { state.recipeId = null; pickADinner(); }
  state.shared = null;
  history.replaceState(null, "", location.pathname + location.search.replace(/[?&]dinner=[^&]*/, "").replace(/^&/, "?"));
  draw();
}
