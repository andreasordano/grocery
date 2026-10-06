// Asking the stores: price the dinner or the list at every store, print the answer,
// and act on taps on the receipt (another store, another product, something from home).
import { feed } from "./dom.js";
import { state } from "./state.js";
import { identity } from "./identity.js";
import { api, logEvent } from "./api.js";
import { dinnerById } from "./dinners.js";
import { redraw } from "./screens.js";
import { idle, printing, failed, showReceipt, reveal } from "./receipt.js";
import { chooseProduct, editPreferences } from "./products.js";

// fresh: a new question, so the receipt prints anew. keepView: stay on the store being looked at.
export async function ask({ fresh = false, keepView = false } = {}) {
  const dinner = state.mode === "dinner";
  const items = dinner ? state.extras : state.items;
  if (dinner ? !state.recipeId : !items.length) return;
  const req = ++state.request;
  const view = keepView ? state.view : null;

  if (fresh || !state.result) {
    printing(dinner ? `${dinnerById(state.recipeId).name} for ${state.servings}`
                    : `${items.length} ${items.length === 1 ? "thing" : "things"} on your list`);
  } else {
    feed.classList.add("busy");  // same question with a change: keep the receipt, dimmed
  }
  try {
    const res = await api("/basket", {
      recipe_id: dinner ? state.recipeId : null, servings: state.servings, items,
      prefs: state.prefs, user_id: identity.userId, session_id: identity.sessionId,
    });
    if (req !== state.request) return;
    feed.classList.remove("busy");
    if (!res.baskets.length || !res.baskets[0].lines.length) {
      idle("No store had these", "Try simpler words, like piim or leib.");
      return;
    }
    const animate = fresh || !state.result;
    state.result = { ...res, id: crypto.randomUUID() };
    showReceipt(view && res.baskets.some(b => b.store === view) ? view : res.store, animate);
    if (animate) reveal();
  } catch {
    if (req === state.request) failed(() => ask({ fresh: true }));
  }
}

const askAgain = () => ask({ keepView: true });

feed.addEventListener("click", e => {
  const store = e.target.closest("[data-store]");
  if (store && store.dataset.store !== state.view) {
    logEvent("view_store", { store: store.dataset.store, recommended_store: state.result.baskets[0].store, result_id: state.result.id });
    showReceipt(store.dataset.store, true);
    return;
  }
  if (e.target.closest("#editPrefs")) { editPreferences(askAgain); return; }
  const pantry = e.target.closest("[data-pantry]");
  if (pantry) {
    state.extras.push(pantry.dataset.pantry);
    logEvent("add_pantry", { item: pantry.dataset.pantry, recipe_id: state.result?.recipe?.id ?? null });
    redraw();
    ask();
    return;
  }
  const line = e.target.closest(".r-line");
  if (line) chooseProduct(line.dataset.key, askAgain);
});
