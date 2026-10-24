// The Dinner screen: how many people, kinds of dinner, a handful of dinners to pick from,
// anything else for the trip, and a dinner someone sent by link.
import { $, pick } from "./dom.js";
import { esc } from "./format.js";
import { state } from "./state.js";
import { storage } from "./storage.js";
import { identity, askName } from "./identity.js";
import { api, logEvent } from "./api.js";
import { shownDinners, shuffle, dinnerById, picked, choose, unpick, MAX_TRIP } from "./dinners.js";
import { bindAdd, itemButton, itemClick } from "./items.js";
import { ask } from "./basket.js";
import { idle, reveal } from "./receipt.js";
import { editDinner } from "./editor-screen.js";

const pickADinner = () => idle(state.trip ? "Pick your dinners" : "Pick a dinner", "Your store and shopping list print here.");

export function open() {
  draw();
  state.recipeId ? ask({ fresh: true }) : pickADinner();
}

// With trips on: the dinners in this trip, each with a way to take it out.
function tripStrip() {
  const ids = picked();
  if (!state.trip || !ids.length) return "";
  const n = ids.length;
  return `<div class="trip">
    <p><b>This trip:</b> ${n} ${n === 1 ? "dinner" : "dinners"}<span class="fine">${n < MAX_TRIP
      ? " · Tap another dinner to add it." : ` · ${MAX_TRIP} is the most for one trip.`}</span></p>
    <ul>${ids.map(id => `<li><span lang="et">${esc(dinnerById(id)?.name ?? "")}</span><button type="button" data-unpick="${esc(id)}"
      aria-label="Take ${esc(dinnerById(id)?.name ?? "")} out of the trip">×</button></li>`).join("")}</ul>
    ${n > 1 ? `<button type="button" class="link" id="clearTrip">Clear</button>` : ""}
    <button type="button" class="btn dark see" id="seeStore">See where to shop <span aria-hidden="true">↓</span></button>
  </div>`;
}

export function draw() {
  const dinners = shownDinners();
  const chosen = picked();
  pick.innerHTML = `
    <h1>${state.trip ? "Dinners" : "Dinner"} <span class="for">for <span class="stepper" role="group" aria-label="Number of people">
        <button type="button" data-step="-1" aria-label="Fewer people">−</button>
        <output id="servings">${state.servings}</output>
        <button type="button" data-step="1" aria-label="More people">+</button>
      </span></span> ${state.trip ? "this week" : "tonight"}</h1>
    ${tripStrip()}
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
      <li${r.id.startsWith("my-") ? ` class="mine"` : ""}><button type="button" class="dish" data-id="${esc(r.id)}" aria-pressed="${chosen.includes(r.id)}">
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
    if (!choose(dish.dataset.id)) return;  // the trip is full: the strip above says so
    if (state.trip) { draw(); logEvent("trip_change", { dinners: picked().length }); }
    else pick.querySelectorAll(".dish").forEach(d => d.setAttribute("aria-pressed", d === dish));
    picked().length ? ask({ fresh: true }) : pickADinner();
    return;
  }
  const out = e.target.closest("[data-unpick]");
  if (out) {
    unpick(out.dataset.unpick);
    draw();
    picked().length ? ask({ fresh: true }) : pickADinner();
    return;
  }
  if (e.target.closest("#seeStore")) { reveal(); return; }
  if (e.target.closest("#clearTrip")) {
    state.tripIds = []; state.recipeId = null;
    draw();
    pickADinner();
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
  const name = await askName();  // first dinner only
  if (name) logEvent("hello", { name });
  try {
    const saved = await api("/my-dinners", { user_id: identity.personId, name: d.name, servings: d.servings, items: d.items,
                                             method: d.method, link: d.link, from_share: d.token });
    state.mine = [...state.mine, saved].sort((a, b) => a.name.localeCompare(b.name));
    d.saved = true;
    draw();
  } catch {
    $("#saveShared").textContent = "Couldn't save. Try again";
  }
}

// Close the sent dinner, and take it out of the address so a reload doesn't bring it back.
function dropShared() {
  if (picked().includes(state.shared.id)) {
    unpick(state.shared.id);
    picked().length ? ask({ fresh: true }) : pickADinner();
  }
  state.shared = null;
  history.replaceState(null, "", location.pathname + location.search.replace(/[?&]dinner=[^&]*/, "").replace(/^&/, "?"));
  draw();
}
