// Asking the stores: price the dinner or the list at every store, print the answer,
// and act on taps on the receipt (another store, another product, something from home).
import { feed } from "./dom.js";
import { state } from "./state.js";
import { identity } from "./identity.js";
import { api, logEvent } from "./api.js";
import { dinnerById, picked } from "./dinners.js";
import { redraw } from "./screens.js";
import { idle, printing, failed, showReceipt, answered } from "./receipt.js";
import { chooseProduct, editPreferences } from "./products.js";
import { bindPeek } from "./peek.js";

// fresh: a new question, so the receipt prints anew. keepView: stay on the store being looked at.
// On phones the receipt is step 2: the bar at the bottom says what it found and goes there (steps.js).
export async function ask({ fresh = false, keepView = false } = {}) {
  const dinner = state.mode === "dinner";
  const items = dinner ? state.extras : state.items;
  const ids = dinner ? picked() : [];
  if (dinner ? !ids.length : !items.length) return;
  const req = ++state.request;
  const view = keepView ? state.view : null;

  if (fresh || !state.result) {
    printing(ids.length > 1 ? `${ids.length} dinners for ${state.servings}`
           : dinner ? `${dinnerById(ids[0]).name} for ${state.servings}`
                    : `${items.length} ${items.length === 1 ? "thing" : "things"} on your list`);
  } else {
    feed.classList.add("busy");  // same question with a change: keep the receipt, dimmed
  }
  try {
    const res = await api("/basket", {
      recipe_id: ids.length === 1 ? ids[0] : null, servings: state.servings, items,
      recipes: ids.length > 1 ? ids.map(id => ({ id, servings: state.servings })) : [],
      prefs: state.prefs, skip: state.skipped.map(s => s.key), user_id: identity.personId, session_id: identity.sessionId, name: identity.name,
    });
    if (req !== state.request) return;
    feed.classList.remove("busy");
    const stores = answered(res);
    if (!stores.length) {  // every store's search failed
      failed(() => ask({ fresh: true }));
      return;
    }
    if (!stores[0].lines.length) {
      idle("No store had these", "Try simpler words, like piim or leib.");
      return;
    }
    const animate = fresh || !state.result;
    state.result = res;
    showReceipt(view && stores.some(b => b.store === view) ? view : res.store, animate);
  } catch {
    if (req === state.request) failed(() => ask({ fresh: true }));
  }
}

const askAgain = () => ask({ keepView: true });
bindPeek(askAgain);

feed.addEventListener("click", e => {
  const store = e.target.closest("[data-store]");
  if (store && store.dataset.store !== state.view) {
    logEvent("view_store", { store: store.dataset.store, recommended_store: state.result.store, result_id: state.result.result_id });
    showReceipt(store.dataset.store, true);
    return;
  }
  if (e.target.closest("[data-prefs]")) { editPreferences(askAgain); return; }
  const pantry = e.target.closest("[data-pantry]");
  if (pantry) {
    state.extras.push(pantry.dataset.pantry);
    logEvent("add_pantry", { item: pantry.dataset.pantry, recipe_id: state.result?.recipe?.id ?? null,
                             recipe_ids: state.result?.dinners?.map(d => d.id) ?? [] });
    redraw();
    ask();
    return;
  }
  // × on a line, or on something no store has: leave it out at every store, and rank them again.
  const skip = e.target.closest("[data-skip]");
  if (skip) {
    const { skip: key, label } = skip.dataset;
    state.skipped = [...state.skipped.filter(s => s.key !== key), { key, label }];
    logEvent("line_removed", { key, store: state.view, result_id: state.result?.result_id });
    ask({ keepView: true });
    return;
  }
  const back = e.target.closest("[data-unskip]");
  if (back) {
    state.skipped = state.skipped.filter(s => s.key !== back.dataset.unskip);
    logEvent("line_restored", { key: back.dataset.unskip, result_id: state.result?.result_id });
    ask({ keepView: true });
    return;
  }
  const line = e.target.closest(".r-line");
  if (line) chooseProduct(line.dataset.key, askAgain);
});
