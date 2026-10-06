// pantryrun's web page: start-up, and the Dinner / Shopping list switch in the top bar.
//
// How the page is put together:
//   screens.js         which screen is on the left; dinner-screen.js, editor-screen.js, list-screen.js are the screens
//   basket.js          asks the stores and acts on taps on the answer; receipt.js draws the answer
//   products.js        choosing another product, and saved preferences
//   items.js           adding and changing items (suggest.js: suggestions while typing)
//   dinners.js         the dinners to choose from; share.js sends one by link
//   state.js           what the page keeps track of; storage.js what the browser remembers
//   identity.js, api.js, dom.js, format.js: who is using it, the server, page elements, formatting
import { $ } from "./dom.js";
import { state } from "./state.js";
import { identity, askName } from "./identity.js";
import { api, logEvent } from "./api.js";
import { addScreen, render } from "./screens.js";
import { idle, failed } from "./receipt.js";
import * as dinnerScreen from "./dinner-screen.js";
import * as editorScreen from "./editor-screen.js";
import * as listScreen from "./list-screen.js";

addScreen("dinner", dinnerScreen);
addScreen("editor", editorScreen);
addScreen("list", listScreen);

// ── the switch: the dark pill slides to the chosen mode ──
const modeSwitch = $(".switch");

function placePill() {
  const on = $('button[aria-pressed="true"]', modeSwitch), pill = $(".pill", modeSwitch);
  pill.style.width = on.offsetWidth + "px";
  pill.style.transform = `translateX(${on.offsetLeft - 3}px)`;
}

modeSwitch.addEventListener("click", e => {
  const b = e.target.closest("button");
  if (!b || b.dataset.mode === state.mode) return;
  state.mode = b.dataset.mode;
  modeSwitch.querySelectorAll("button").forEach(x => x.setAttribute("aria-pressed", x === b));
  placePill();
  state.result = null;
  render();
});
addEventListener("resize", placePill);

// ── start: the name (first visit only), the dinners, your own dinners, a dinner sent by link ──
async function start() {
  placePill();
  document.fonts?.ready.then(placePill);
  idle("Getting the dinners", "One moment.");
  const named = identity.userId ? Promise.resolve() : askName().then(() => logEvent("hello", {}));
  try {
    const { recipes, dishes, categories } = await api("/recipes");
    Object.assign(state, { recipes, dishes, categories });
    if (!["ideas", "classics", "mine", ...categories.map(c => c.id)].includes(state.category)) state.category = "ideas";
    await named;
    state.mine = (await api(`/my-dinners?user_id=${encodeURIComponent(identity.userId)}`).catch(() => ({ dinners: [] }))).dinners;
    const token = new URLSearchParams(location.search).get("dinner");
    if (token) {
      state.shared = await api(`/shares/${encodeURIComponent(token)}?user_id=${encodeURIComponent(identity.userId)}`).catch(() => null);
      if (state.shared) state.recipeId = state.shared.id;
    }
    render();
    if (token && !state.shared) idle("This link doesn't lead to a dinner", "It may be mistyped. Pick a dinner here instead.");
  } catch {
    failed(() => location.reload());
  }
}

start();
