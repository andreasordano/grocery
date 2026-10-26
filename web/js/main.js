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
import { identity, askName, askUsualStore } from "./identity.js";
import { api, logEvent } from "./api.js";
import { setStores } from "./format.js";
import { addScreen, render } from "./screens.js";
import { idle, failed } from "./receipt.js";
import { add } from "./dinners.js";
import { offerNewsletter } from "./newsletter.js";
import { startFooter } from "./footer.js";
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
  state.step = 1;
  render();
});
addEventListener("resize", placePill);

// ── start: the visit, the dinners, your own dinners, a dinner sent by link, a weekly plan ──
async function start() {
  placePill();
  document.fonts?.ready.then(placePill);
  idle("Getting the dinners", "One moment.");
  const params = new URLSearchParams(location.search);
  const token = params.get("dinner"), planToken = params.get("plan");
  // where a link came from: the newsletter or a social post (?from=newsletter, instagram, fb-<group>)
  const tagged = /^[a-z0-9-]{1,30}$/.test(params.get("from") ?? "") ? params.get("from") : null;
  const from = tagged ?? (identity.fromTesterLink ? "tester_link" : token ? "shared_dinner" : planToken ? "plan" : "direct");
  logEvent("visit", {
    from, dinner_token: token, plan: planToken, first_visit: identity.firstVisit, referrer: document.referrer || null,
  });
  // the dinners, and the stores as the server names them (needed by the usual-store question and receipts)
  const loaded = api("/recipes").then(data => { setStores(data); startFooter(); return data; });
  // first visit: who's this, where do they usually shop, and would they like the weekly plan?
  askName()
    .then(name => { if (name) logEvent("hello", { name }); })
    .then(() => loaded.catch(() => null))
    .then(askUsualStore)
    .then(store => { if (store !== undefined) logEvent("usual_store", { store, changed: false }); })
    .then(() => { if (tagged !== "newsletter") return offerNewsletter(); });  // once per browser
  try {
    const mine = api(`/my-dinners?user_id=${encodeURIComponent(identity.personId)}`).catch(() => ({ dinners: [] }));  // at the same time
    const { recipes, dishes, categories } = await loaded;
    Object.assign(state, { recipes, dishes, categories });
    if (!["ideas", "classics", "mine", ...categories.map(c => c.id)].includes(state.category)) state.category = "ideas";
    state.mine = (await mine).dinners;
    if (token) {
      state.shared = await api(`/shares/${encodeURIComponent(token)}?user_id=${encodeURIComponent(identity.personId)}`).catch(() => null);
      if (state.shared) add(state.shared.id);
    }
    if (planToken) {
      state.plan = await api(`/plans/${encodeURIComponent(planToken)}?user_id=${encodeURIComponent(identity.personId)}`
                             + (tagged ? `&came_from=${tagged}` : "")).catch(() => null);
      state.plan?.dinners.forEach(d => add(d.id));
    }
    render();
    if (token && !state.shared) idle("This link doesn't lead to a dinner", "It may be mistyped. Pick a dinner here instead.");
    if (planToken && !state.plan) idle("This link doesn't lead to a plan", "It may be mistyped. Pick a dinner here instead.");
  } catch {
    failed(() => location.reload());
  }
}

start();
