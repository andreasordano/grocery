// The page's foot: what pantryrun knows about you (where you usually shop, your product preferences),
// the weekly plan sign-up, and where the prices and dishes come from. These used to sit under the receipt.
import { $ } from "./dom.js";
import { esc, chains, storeNames, allStores } from "./format.js";
import { state } from "./state.js";
import { identity, askUsualStore } from "./identity.js";
import { logEvent } from "./api.js";
import { newsletterBox, bindNewsletterBox } from "./newsletter.js";
import { editPreferences } from "./products.js";
import { ask } from "./basket.js";
import { showReceipt } from "./receipt.js";

const you = $("#footYou");

// Once the stores are known: the sources and the sign-up (drawn once, so a half-typed address stays).
export function startFooter() {
  if (allStores().length) $("#footStores").textContent = `Prices from the ${storeNames(allStores())} e-shops.`;
  $("#footNews").innerHTML = newsletterBox("footer");
  bindNewsletterBox("footer");
  refreshFooter();
}

// You: drawn again when the usual store or the preferences change.
export function refreshFooter() {
  const usual = chains()[identity.usualStore];
  const n = Object.keys(state.prefs).length;
  you.innerHTML = `<h2>You</h2>
    <p>Usual store: ${usual ? esc(usual) : identity.usualStore === "other" ? "another store" : "not said yet"} ·
      <button type="button" class="link" id="changeUsual">${usual || identity.usualStore === "other" ? "Change" : "Tell us"}</button></p>
    <p>${n ? `${n} product ${n === 1 ? "preference" : "preferences"} · <button type="button" class="link" data-prefs>Edit</button>`
      : "No product preferences yet. Tap a product on the receipt to choose another."}</p>`;
}

you.addEventListener("click", e => {
  if (e.target.closest("#changeUsual")) {
    identity.usualStore = undefined;  // ask again
    askUsualStore().then(store => {
      logEvent("usual_store", { store, changed: true });
      refreshFooter();
      if (state.result && state.status === "answer") showReceipt(state.view, false);  // "Your usual store" on the receipt
    });
    return;
  }
  if (e.target.closest("[data-prefs]")) editPreferences(() => state.result ? ask({ keepView: true }) : refreshFooter());
});
