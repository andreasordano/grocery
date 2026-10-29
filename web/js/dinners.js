// The dinners to choose from: hand-written classics, pantryrun's own and store recipes under their chips,
// this person's own dinners, one sent by link, and a weekly plan's.
import { state } from "./state.js";

const SHOWN = 6;  // dinners on screen at once
export const MAX_TRIP = 5;  // dinners in one trip (the server's limit too)

// The dinners being priced: every dinner in this trip.
export const picked = () => state.tripIds;

const synced = () => { state.recipeId = state.tripIds.at(-1) ?? null; };

// Pick a dinner: it joins the trip. False when the trip is full.
export function add(id) {
  if (!state.tripIds.includes(id)) {
    if (state.tripIds.length >= MAX_TRIP) return false;
    state.tripIds = [...state.tripIds, id];
  }
  synced();
  return true;
}

export function unpick(id) {
  state.tripIds = state.tripIds.filter(x => x !== id);
  synced();
}

// A tap on a dinner: pick it; a dinner already in the trip comes out of it.
export function choose(id) {
  if (state.tripIds.includes(id)) { unpick(id); return true; }
  return add(id);
}

export function dinnerById(id) {
  const d = state.dishes.find(x => x.id === id);
  if (d) return d;
  if (state.shared && id === state.shared.id) return state.shared;
  const planned = state.plan?.dinners.find(x => x.id === id && x.name);  // only dinners sent by link come whole
  if (planned) return planned;
  return state.mine.find(x => x.id === id) || state.recipes.find(r => r.id === id);
}

function pool(category) {
  if (category === "mine") return state.mine.map(r => r.id);
  if (category === "classics") return state.recipes.map(r => r.id);
  if (category === "ideas") return [...state.recipes, ...state.dishes].map(r => r.id);
  return [...state.recipes, ...state.dishes].filter(d => d.tags?.includes(category)).map(d => d.id);
}

// A random handful from the category; "Show me others" avoids repeating what was just on screen.
export function shuffle(avoid = []) {
  const ids = pool(state.category);
  if (state.category === "classics" || state.category === "mine") { state.shown = ids; return; }
  const fresh = ids.filter(id => !avoid.includes(id));
  const from = fresh.length >= SHOWN ? fresh : ids;
  const shown = [...from].sort(() => Math.random() - 0.5).slice(0, SHOWN);
  // Keep the chosen dinners on screen so their buttons stay pressed.
  const keep = picked().filter(id => ids.includes(id) && !shown.includes(id));
  keep.forEach((id, i) => { shown[i] = id; });
  state.shown = shown;
}

export function shownDinners() {
  if (!state.shown.length) shuffle();
  return state.shown.map(dinnerById).filter(Boolean);
}
