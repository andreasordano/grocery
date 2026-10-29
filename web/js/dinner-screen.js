// The Dinner screen: how many people, kinds of dinner, a handful of dinners to pick from,
// anything else for the trip, a dinner someone sent by link, and a weekly plan from the newsletter.
// Tapping a dinner opens its own page (what's in it, how to cook it); "Add to this trip" puts it in the trip.
// Under the trip: each dinner's recipe card and the weekly plan sign-up (recipe.js).
import { $, pick, heroText } from "./dom.js";
import { esc } from "./format.js";
import { state } from "./state.js";
import { storage } from "./storage.js";
import { identity } from "./identity.js";
import { api, logEvent } from "./api.js";
import { shownDinners, shuffle, dinnerById, picked, choose, unpick, MAX_TRIP } from "./dinners.js";
import { bindAdd, itemButton, itemClick } from "./items.js";
import { ask } from "./basket.js";
import { idle } from "./receipt.js";
import { editDinner } from "./editor-screen.js";
import { recipeBody, recipeActions, hasPhoto } from "./recipe.js";
import { refreshSteps } from "./steps.js";
import { storeNames, allStores } from "./format.js";

const pickADinner = () => idle("Pick a dinner", "Where it’s cheapest prints here, with your shopping list.");

export function open() {
  draw();
  state.recipeId ? ask({ fresh: true }) : pickADinner();
}

// The dinners in this trip, each with a way to take it out.
function tripStrip() {
  const ids = picked();
  if (!ids.length) return "";
  const n = ids.length;
  return `<div class="trip">
    <p><b>Your basket:</b> ${n} ${n === 1 ? "dinner" : "dinners"}<span class="fine">${n < MAX_TRIP
      ? " · Add another one below." : ` · ${MAX_TRIP} is the most for one basket.`}</span></p>
    <ul>${ids.map(id => `<li><span lang="et">${esc(dinnerById(id)?.name ?? "")}</span>${featured(id)
      ? `<span class="featured">Featured</span>` : ""}<button type="button" class="open" data-open="${esc(id)}">Recipe</button><button type="button" data-unpick="${esc(id)}"
      aria-label="Take ${esc(dinnerById(id)?.name ?? "")} out of the basket">×</button></li>`).join("")}</ul>
    ${n > 1 ? `<button type="button" class="link" id="clearTrip">Clear</button>` : ""}
  </div>`;
}

// The plan's featured dinner: an unpaid pick from a store's or brand's recipes, always labelled.
const featured = id => state.plan?.dinners.some(d => d.id === id && d.featured);

const ICON = {
  look: `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round"><circle cx="10.5" cy="10.5" r="6"/><path d="m15 15 5 5"/></svg>`,
  plus: `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.6" stroke-linecap="round"><path d="M12 5v14M5 12h14"/></svg>`,
  tick: `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.6" stroke-linecap="round" stroke-linejoin="round"><path d="m5 12.5 4.5 4.5L19 7.5"/></svg>`,
};
const CATEGORY_EMOJI = { soup: "🍲", fish: "🐟", chicken: "🍗", mince: "🥘", meat: "🥩", veggie: "🥦" };

// One dinner to pick: its photo (or a sticker), name, time and how many things to buy. The card opens the
// recipe; the round + on the photo puts it in the basket (a tick takes it out again).
function dinnerCard(r, inBasket) {
  const own = r.id.startsWith("my-"), name = esc(r.name);
  const count = r.count ?? r.items?.length;
  const meta = [r.minutes ? `${r.minutes} min` : "", count ? `${count} to buy` : ""].filter(Boolean).join(" · ");
  const photo = r.photo || (own && hasPhoto(r) ? r.image : "");
  return `<li class="dc${own ? " mine" : ""}${inBasket ? " in" : ""}">
    <button type="button" class="dish" data-id="${esc(r.id)}" aria-label="${name}: see the recipe">
      <span class="dc-photo">${photo ? `<img src="${esc(photo)}" alt="" loading="lazy" referrerpolicy="no-referrer">`
        : `<span class="dc-emoji" aria-hidden="true">${r.emoji ?? CATEGORY_EMOJI[r.category] ?? "🍽️"}</span>`}</span>
      <span class="dc-name" lang="et">${name}</span>
      ${r.label ? `<span class="dc-label">${esc(r.label)}</span>` : ""}
      ${meta ? `<span class="dc-meta">${meta}</span>` : ""}
      <span class="dc-look">${ICON.look}${own ? "Recipe" : "See the recipe"}</span>
    </button>
    <button type="button" class="dc-add" data-add="${esc(r.id)}" aria-pressed="${inBasket}"
      aria-label="${inBasket ? `Take ${name} out of the basket` : `Add ${name} to the basket`}">${inBasket ? ICON.tick : ICON.plus}</button>
    ${own ? `<button type="button" class="link dc-edit" data-edit-dinner="${esc(r.id)}" aria-label="Edit ${name}">Edit</button>` : ""}
  </li>`;
}

const stepper = () => `<span class="stepper" role="group" aria-label="Number of people">
        <button type="button" data-step="-1" aria-label="Fewer people">−</button>
        <output id="servings">${state.servings}</output>
        <button type="button" data-step="1" aria-label="More people">+</button>
      </span>`;

// A dinner's own page: its photo, what goes in for this many people, how to cook it, and adding it to the trip.
function drawDetail() {
  const v = state.viewing, d = v.card, name = d?.name ?? dinnerById(v.id)?.name ?? "";
  const inTrip = picked().includes(v.id), n = d?.ingredients.length ?? 0;
  heroText.innerHTML = "";
  pick.innerHTML = `
    <article class="dinner-page">
      <button type="button" class="link back" id="backToList"><span aria-hidden="true">←</span> All dinners</button>
      ${d && hasPhoto(d) ? `<div class="dp-photo"><img src="${esc(d.image)}" alt="" referrerpolicy="no-referrer"></div>` : ""}
      <h1 class="dp-name" lang="et">${esc(name)}</h1>
      ${d?.about ? `<p class="dp-about">${esc(d.about)}</p>` : ""}
      <p class="dp-sub">For ${stepper()} ${state.servings === 1 ? "person" : "people"}${d ? ` · ${n} to buy` : ""}${d?.minutes ? ` · ${d.minutes} min` : ""}</p>
      <div class="dp-add">${inTrip
        ? `<span class="in-trip">In your basket</span><button type="button" class="link" id="takeOut">Take it out</button>`
        : `<button type="button" class="btn dark" id="addToTrip">${ICON.plus}Add to the basket</button>`}
        <span class="fine" id="tripFull" role="status"></span></div>
      ${d ? `<div class="dp-recipe">${recipeBody(d)}</div>${recipeActions(d)}`
        : v.failed ? `<p class="fine">Couldn't get the recipe. <button type="button" class="link" id="retryCard">Try again</button></p>`
        : `<p class="fine">Getting the recipe…</p>`}
    </article>`;
  pick.onclick = onClick;
}

async function loadCard() {
  const v = state.viewing;
  try {
    const card = await api(`/recipes/${encodeURIComponent(v.id)}/card?servings=${state.servings}&user_id=${encodeURIComponent(identity.personId)}`);
    if (state.viewing === v) { v.card = card; v.failed = false; draw(); }
  } catch {
    if (state.viewing === v) { v.failed = true; draw(); }
  }
}

function openDinner(id) {
  state.viewing = { id, card: null };
  draw();
  scrollTo({ top: 0 });
  logEvent("dinner_view", { id });
  loadCard();
}

function backToList() {
  state.viewing = null;
  draw();
  scrollTo({ top: 0 });
}

export function draw() {
  if (state.viewing) { drawDetail(); return; }
  const dinners = shownDinners();
  const chosen = picked(), several = chosen.length > 1;
  heroText.innerHTML = `
    <h1>${several ? "Dinners" : "Dinner"} <span class="for">for ${stepper()}</span> ${several ? "this week" : "tonight"}</h1>
    <p class="sub">Pick what you’ll cook. pantryrun prices it at ${allStores().length ? esc(storeNames(allStores())) : "the stores"}
      and tells you where the whole basket costs least.</p>`;
  heroText.onclick = onClick;
  pick.innerHTML = `
    <h2 class="card-title"><span class="num" aria-hidden="true">1</span>Pick your dinners</h2>
    <p class="card-sub">One for tonight, or up to ${MAX_TRIP} for the week. They’re priced together, as one basket.</p>
    ${tripStrip()}
    ${state.shared ? `<div class="sent">
      <p><span class="what">A dinner sent to you</span><span class="name" lang="et">${esc(state.shared.name)}</span></p>
      <span class="btns">${state.shared.saved ? `<span class="fine">Saved to Mine</span>`
        : `<button type="button" class="btn quiet" id="saveShared">Save to my dinners</button>`}
        <button type="button" class="x" id="dropShared" aria-label="Close">×</button></span>
    </div>` : ""}
    ${state.plan ? `<div class="sent">
      <p><span class="what">This week's plan</span><span class="name">${esc(state.plan.title)}</span></p>
      <span class="btns"><button type="button" class="x" id="dropPlan" aria-label="Close the plan">×</button></span>
    </div>` : ""}
    <div class="chips cats" role="group" aria-label="Kind of dinner">${[
      { id: "ideas", name: "Ideas" }, ...state.categories.filter(c => c.moment), { id: "mine", name: "Mine" },
      ...state.categories.filter(c => !c.moment), { id: "classics", name: "Classics" },
    ].map(c => `<button type="button" data-cat="${esc(c.id)}" aria-pressed="${c.id === state.category}">${esc(c.name)}</button>`).join("")}</div>
    ${state.category === "mine" && !state.mine.length ? `<p class="empty">Write down a dinner you cook often. Type what you
      buy for it once, with amounts if you like, or start from a recipe you found online. pantryrun finds the store each time.</p>` : ""}
    <ul class="dishes">${dinners.map(r => dinnerCard(r, chosen.includes(r.id))).join("")}</ul>
    <p class="fine dishes-note" id="dishesNote" role="status"></p>
    <div class="more">${state.category === "mine" ? `<span class="btns"><button type="button" class="btn quiet" id="newDinner">New dinner</button>
      <button type="button" class="link" id="fromLinkDinner">From a recipe link</button></span>`
      : state.category === "classics" ? ""
      : `<button type="button" class="link" id="shuffle">Show me others</button>`}
</div>
    <div class="extras">${state.extrasOpen || state.extras.length ? `
      <h3>Anything else to buy?</h3>
      <form class="field" id="add" autocomplete="off">
        <input id="item" placeholder="kohv, leib, banaanid 1kg" aria-label="Add more items" enterkeyhint="done">
        <button class="btn quiet" type="submit">Add</button>
      </form>
      ${state.extras.length ? `<ul class="tags">${state.extras.map((it, i) => `
        <li>${itemButton(it, i)}<button type="button" data-remove="${i}" aria-label="Remove ${esc(it)}">×</button></li>`).join("")}</ul>` : ""}`
      : `<div class="extras-ask"><div><h3>Anything else to buy?</h3><p class="fine">Coffee, milk, toilet paper: it goes in the same basket.</p></div>
        <button type="button" class="btn quiet add-more" id="openExtras"><span aria-hidden="true">+</span>Add items</button></div>`}
    </div>`;
  if (state.extrasOpen || state.extras.length) bindAdd(state.extras, extrasChanged);
  pick.onclick = onClick;
  refreshSteps();
}

// After the extras change: redraw, and price the dinner again if one is picked.
function extrasChanged() {
  draw();
  if (state.recipeId) ask();
}

// The + on a dinner's card: into the basket, or out of it when it's there.
function toggle(id) {
  if (!choose(id)) {  // the basket is full
    $("#dishesNote").textContent = `${MAX_TRIP} dinners is the most for one basket. Take one out first.`;
    return;
  }
  logEvent("trip_change", { dinners: picked().length, from: "card" });
  draw();
  picked().length ? ask({ fresh: true }) : pickADinner();
}

let stepTimer;

function onClick(e) {
  const recipe = e.target.closest("[data-open]");
  if (recipe) { openDinner(recipe.dataset.open); return; }
  const dish = e.target.closest(".dish");
  if (dish) { openDinner(dish.dataset.id); return; }
  const add = e.target.closest("[data-add]");
  if (add) { toggle(add.dataset.add); return; }
  if (e.target.closest("#backToList")) { backToList(); return; }
  if (e.target.closest("#retryCard")) { state.viewing.failed = false; draw(); loadCard(); return; }
  if (e.target.closest("#addToTrip")) {
    if (!choose(state.viewing.id)) {  // the trip is full
      $("#tripFull").textContent = `${MAX_TRIP} dinners is the most for one basket. Take one out first.`;
      return;
    }
    logEvent("trip_change", { dinners: picked().length });
    backToList();
    ask({ fresh: true });
    return;
  }
  if (e.target.closest("#takeOut")) {
    unpick(state.viewing.id);
    logEvent("trip_change", { dinners: picked().length });
    draw();
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
  if (e.target.closest("#clearTrip")) {
    state.tripIds = []; state.recipeId = null; state.skipped = [];
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
    stepTimer = setTimeout(() => {  // wait for the last tap
      if (state.viewing) loadCard();
      if (state.recipeId) ask();
    }, 350);
    return;
  }
  if (itemClick(e, state.extras, extrasChanged)) return;
  const editOwn = e.target.closest("[data-edit-dinner]");
  if (editOwn) { editDinner(editOwn.dataset.editDinner); return; }
  if (e.target.closest("#newDinner")) { editDinner(null); return; }
  if (e.target.closest("#fromLinkDinner")) { editDinner(null, { fromLink: true }); return; }
  if (e.target.closest("#openExtras")) { state.extrasOpen = true; draw(); $("#item").focus(); return; }
  if (e.target.closest("#saveShared")) { saveShared(); return; }
  if (e.target.closest("#dropShared")) dropShared();
  if (e.target.closest("#dropPlan")) dropPlan();
}

async function saveShared() {
  const d = state.shared;
  try {
    const saved = await api("/my-dinners", { user_id: identity.personId, name: d.name, servings: d.servings, items: d.items,
                                             method: d.method, link: d.link, image: d.image, from_share: d.token });
    state.mine = [...state.mine, saved].sort((a, b) => a.name.localeCompare(b.name));
    d.saved = true;
    draw();
  } catch {
    $("#saveShared").textContent = "Couldn't save. Try again";
  }
}

// Close the weekly plan: its dinners leave the trip, and the address forgets it.
function dropPlan() {
  state.plan.dinners.forEach(d => unpick(d.id));
  state.plan = null;
  picked().length ? ask({ fresh: true }) : pickADinner();
  history.replaceState(null, "", location.pathname + location.search.replace(/[?&](plan|from)=[^&]*/g, "").replace(/^&/, "?"));
  draw();
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
