// The At the store screen (WEB-29): you're in a store, or about to go in. Pick which one, and pantryrun shows three
// dinners built on what's on sale there this week (core/deals.py, GET /deals). Tapping one prices it at that
// store only: the receipt is that store's shopping list.
import { $, pick, heroText } from "./dom.js";
import { esc, shopName, allStores, storeOfChain } from "./format.js";
import { state } from "./state.js";
import { storage } from "./storage.js";
import { identity } from "./identity.js";
import { api, logEvent } from "./api.js";
import { dinnerById, setPeople } from "./dinners.js";
import { ask } from "./basket.js";
import { idle } from "./receipt.js";
import { refreshSteps } from "./steps.js";

const SHOWN = 3;

// The store's deal dinners the page knows (a dinner the page doesn't list, e.g. one archived since, is left out).
const dealsAt = store => (state.deals?.stores[store] ?? []).filter(d => dinnerById(d.id));
const onScreen = () => dealsAt(state.atStore).slice(state.dealsFrom, state.dealsFrom + SHOWN);

const pickOne = () => idle("Pick tonight's dinner", `Your shopping list at ${shopName(state.atStore)} prints here.`);
const pickStore = () => idle("Which store are you at?", "Pick it, and see three dinners built on its deals.");

export function open() {
  // First time here: the usual store, when it's one pantryrun prices.
  const remembered = allStores().includes(state.atStore);
  if (!remembered) state.atStore = storeOfChain(identity.usualStore);
  const how = remembered ? "again" : "usual";
  draw();
  if (!state.deals) load(how);
  else if (state.atStore) shown(how);
  if (state.tonight && state.deals) ask({ fresh: true });
  else if (state.atStore) pickOne();
  else pickStore();
}

async function load(how) {
  try {
    state.deals = await api("/deals");
  } catch {
    state.deals = { at: null, stores: {}, failed: true };
  }
  if (state.mode !== "store") return;
  draw();
  if (state.atStore) shown(how);
}

// Which dinners were put in front of someone, for reading the answers (deal_pick) against.
function shown(how) {
  if (!state.deals?.at) return;
  logEvent("deals_store", { store: state.atStore, how, dinners: onScreen().map(d => d.id), from: state.dealsFrom });
}

function dealCard(d, rank) {
  const r = dinnerById(d.id), name = esc(r.name), on = d.id === state.tonight;
  const sale = d.on_sale.slice(0, 3).map(s => `${esc(s.label)}${s.off ? ` −${s.off}%` : ""}`).join(", ");
  return `<li class="deal${on ? " in" : ""}">
    <button type="button" class="deal-pick" data-tonight="${esc(d.id)}" data-rank="${rank}" aria-pressed="${on}">
      <span class="deal-photo">${r.photo ? `<img src="${esc(r.photo)}" alt="" loading="lazy" referrerpolicy="no-referrer">`
        : `<span class="dc-emoji" aria-hidden="true">${r.emoji ?? "🍽️"}</span>`}</span>
      <span class="deal-text">
        <span class="deal-name" lang="et">${name}</span>
        <span class="deal-off">${d.on_sale.length} of ${d.count} on sale</span>
        <span class="deal-what" lang="et">${sale}${d.on_sale.length > 3 ? "…" : ""}</span>
        ${r.minutes ? `<span class="deal-meta">${r.minutes} min</span>` : ""}
      </span>
      <span class="deal-tick" aria-hidden="true">${on ? "Tonight" : "Pick"}</span>
    </button>
  </li>`;
}

function list() {
  if (!state.atStore) return "";
  const where = esc(shopName(state.atStore));
  if (!state.deals) return `<p class="fine">Getting this week's deals…</p>`;
  if (state.deals.failed) return `<p class="fine">Couldn't get this week's deals. <button type="button" class="link" id="retryDeals">Try again</button></p>`;
  if (!state.deals.at) return `<p class="empty">pantryrun is still working out this week's deals. Try again in a few minutes.
    <button type="button" class="link" id="retryDeals">Try again</button></p>`;
  const all = dealsAt(state.atStore);
  if (!all.length) return `<p class="empty">Nothing on sale at ${where} makes a whole dinner this week. Try another store,
    or pick any dinner under Dinner.</p>`;
  return `<h3 class="deals-title">On sale at ${where} this week</h3>
    <ol class="deals">${onScreen().map((d, i) => dealCard(d, state.dealsFrom + i + 1)).join("")}</ol>
    ${all.length > SHOWN ? `<div class="more"><button type="button" class="link" id="moreDeals">Show me others</button></div>` : ""}`;
}

const stepper = n => `<span class="stepper" role="group" aria-label="Number of people">
        <button type="button" data-step="-1" aria-label="Fewer people">−</button>
        <output id="servings">${n}</output>
        <button type="button" data-step="1" aria-label="More people">+</button>
      </span>`;

export function draw() {
  heroText.innerHTML = state.atStore
    ? `<h1>Tonight at ${esc(shopName(state.atStore))} <span class="for">for ${stepper(state.servings)}</span></h1>
      <p class="sub">Three dinners built on what’s on sale there this week, with the list for that store.</p>`
    : `<h1>At the store?</h1>
      <p class="sub">Tell pantryrun which store you’re in. It shows dinners built on that store’s deals this week.</p>`;
  heroText.onclick = onClick;
  pick.innerHTML = `
    <h2 class="card-title"><span class="num" aria-hidden="true">1</span>Which store are you at?</h2>
    <div class="chips at-store" role="group" aria-label="The store you're at">${allStores().map(s =>
      `<button type="button" data-at="${esc(s)}" aria-pressed="${s === state.atStore}">${esc(shopName(s))}</button>`).join("")}</div>
    ${list()}`;
  pick.onclick = onClick;
  refreshSteps();
}

let stepTimer;

function onClick(e) {
  const at = e.target.closest("[data-at]");
  if (at && at.dataset.at !== state.atStore) {
    state.atStore = at.dataset.at;
    storage.set("pantryrun.atStore", state.atStore);
    state.dealsFrom = 0;
    state.tonight = null;
    state.result = null;
    draw();
    pickOne();
    shown("tap");
    return;
  }
  const dinner = e.target.closest("[data-tonight]");
  if (dinner) {
    const id = dinner.dataset.tonight;
    if (id === state.tonight) return;
    state.tonight = id;
    setPeople(id, state.servings);  // for the headline's number, not the recipe's own (a Rimi recipe can be for 10)
    logEvent("deal_pick", { store: state.atStore, id, rank: +dinner.dataset.rank });
    draw();
    ask({ fresh: true });
    return;
  }
  if (e.target.closest("#moreDeals")) {
    const n = dealsAt(state.atStore).length;
    state.dealsFrom = state.dealsFrom + SHOWN >= n ? 0 : state.dealsFrom + SHOWN;
    draw();
    shown("more");
    return;
  }
  if (e.target.closest("#retryDeals")) {
    state.deals = null;
    draw();
    load("again");
    return;
  }
  const step = e.target.closest("[data-step]");
  if (step) {
    const n = Math.min(12, Math.max(1, Number($("#servings").textContent) + +step.dataset.step));
    state.servings = n;
    if (state.tonight) setPeople(state.tonight, n);
    $("#servings").textContent = n;
    clearTimeout(stepTimer);
    stepTimer = setTimeout(() => { if (state.tonight) ask(); }, 350);  // wait for the last tap
  }
}
