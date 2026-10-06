// The dinners to choose from: hand-written classics, NutriData dishes by category,
// this person's own dinners, and one sent by link.
import { state } from "./state.js";

const SHOWN = 6;  // dinners on screen at once

export function dinnerById(id) {
  const d = state.dishes.find(x => x.id === id);
  if (d) return d;
  if (state.shared && id === state.shared.id) return state.shared;
  return state.mine.find(x => x.id === id) || state.recipes.find(r => r.id === id);
}

function pool(category) {
  if (category === "mine") return state.mine.map(r => r.id);
  if (category === "classics") return state.recipes.map(r => r.id);
  if (category === "ideas") return [...state.recipes, ...state.dishes].map(r => r.id);
  return state.dishes.filter(d => d.category === category).map(d => d.id);
}

// A random handful from the category; "Show me others" avoids repeating what was just on screen.
export function shuffle(avoid = []) {
  const ids = pool(state.category);
  if (state.category === "classics" || state.category === "mine") { state.shown = ids; return; }
  const fresh = ids.filter(id => !avoid.includes(id));
  const from = fresh.length >= SHOWN ? fresh : ids;
  const picked = [...from].sort(() => Math.random() - 0.5).slice(0, SHOWN);
  // Keep the chosen dinner on screen so its button stays pressed.
  if (state.recipeId && ids.includes(state.recipeId) && !picked.includes(state.recipeId)) picked[0] = state.recipeId;
  state.shown = picked;
}

export function shownDinners() {
  if (!state.shown.length) shuffle();
  return state.shown.map(dinnerById).filter(Boolean);
}
