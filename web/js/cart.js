// Sending the basket to the store's e-shop, for people who shop online. Stores don't let another site
// fill their cart, so there are three ways, shown in the sheet: open each product, pantryrun's browser
// extension (extension/, Rimi only, computers only), or one tap once a store works with us (would you
// use it?). With the extension, "Order online at Rimi" fills the cart straight away.
// Also a fake door for delivery (WEB-39): would people rather have the list delivered by Wolt or Bolt?
// Neither takes a list from other apps yet; the answers measure demand before asking them (PROD-18).
import { $, after, sheet, sheetForm } from "./dom.js";
import { cap, esc, num, eshopName } from "./format.js";
import { state } from "./state.js";
import { logEvent } from "./api.js";
import { storage } from "./storage.js";

const extension = () => (document.documentElement.dataset.pantryrunCart || "").split(" ").includes("rimi");
const phone = () => matchMedia("(pointer: coarse)").matches;

// The receipt's products as the cart takes them: the store's product id and how many (or kg).
const cartItems = b => b.lines.filter(l => l.store_id && l.cart_qty)
  .map(l => ({ id: String(l.store_id), qty: +l.cart_qty, name: l.product }));

const qtyLabel = l => l.packs ? `${l.packs} ×` : l.cart_qty ? `${num.format(l.cart_qty)} kg` : "";

// ── "Get it delivered instead?" Asked once per person: in the cart sheet, or after "Delivered by Wolt or Bolt"
// under "How will you get it?", whichever comes first.
const deliveryAnswered = () => storage.get("pantryrun.delivery", null) !== null;
const DELIVERY_THANKS = "Thanks. Every yes helps us ask Wolt and Bolt.";

function deliveryAsk() {
  if (deliveryAnswered()) return "";
  return `<section class="delivery-ask"><h3>Get it delivered instead?</h3>
      <p class="fine">Wolt and Bolt don't take a list from other apps yet. Would you use it with one of them?</p>
      <span class="btns"><button type="button" class="btn quiet" data-delivery="wolt">Wolt</button>
        <button type="button" class="btn quiet" data-delivery="bolt">Bolt</button>
        <button type="button" class="link" data-delivery="none">No, I'll go to the store</button></span></section>`;
}

// After "Delivered by Wolt or Bolt": which one, unless they said before.
export function deliveryFollowUp() {
  const before = storage.get("pantryrun.delivery", null);
  if (before === "wolt" || before === "bolt") return `<p>${DELIVERY_THANKS}</p>`;
  return `<div class="delivery-ask"><p>Neither can do it yet. Which one would you use?</p>
    <span class="btns"><button type="button" class="btn quiet" data-delivery="wolt">Wolt</button>
      <button type="button" class="btn quiet" data-delivery="bolt">Bolt</button></span></div>`;
}

function answerDelivery(button, where) {
  const service = button.dataset.delivery;
  storage.set("pantryrun.delivery", service);
  const b = state.result?.baskets.find(x => x.store === state.view) ?? state.result?.baskets[0];
  logEvent("delivery_interest", { service, where, store: b?.store ?? null, result_id: state.result?.result_id ?? null });
  document.querySelectorAll(".delivery-ask").forEach(box => {
    box.innerHTML = `<p${where === "sheet" ? ` class="fine"` : ""}>${service === "none" ? "Thanks for saying." : DELIVERY_THANKS}</p>`;
  });
}

function fill(b, items, data, note) {
  window.postMessage({ source: "pantryrun", type: "fill-cart", store: "rimi", items }, location.origin);
  logEvent("cart_send", { ...data, via: "extension" });
  const byHand = b.lines.length - items.length;
  note.innerHTML = `<p>Opening Rimi in a new tab. Your cart fills in a moment${byHand
    ? `; ${byHand} ${byHand === 1 ? "product" : "products"} you'll add by hand` : ""}.</p>`;
}

// One-go filling: what this person can do with it, on this device and at this store.
function extensionWay(store) {
  if (store !== "rimi") return `<p class="fine">Only for Rimi so far.</p>`;
  if (phone()) return `<p class="fine">Only on a computer, in Chrome or Edge: phones don't run browser extensions.</p>`;
  return `<p class="fine">pantryrun's browser extension for Chrome or Edge adds everything on rimi.ee, in your own browser.
      Your Rimi login never reaches pantryrun. It's in testing, so it isn't in the Chrome Web Store yet.</p>
    <ol class="cart-steps">
      <li><a href="/extension.zip" download id="getExtension">Download the extension</a> and unzip it.</li>
      <li>Open <code>chrome://extensions</code> (Edge: <code>edge://extensions</code>) and turn on <b>Developer mode</b>.</li>
      <li>Click <b>Load unpacked</b> and choose the unzipped folder. Then reload this page and send again.</li>
    </ol>`;
}

function ways(b, data) {
  const linked = b.lines.filter(l => l.url);
  sheetForm.innerHTML = `
    <div class="sh-top">
      <h2 id="sheetTitle">Shopping online at ${esc(eshopName(b.store))}?</h2>
      <p>Stores don't let other sites fill their cart yet, so pantryrun can't do it on its own. Here's what works today.</p>
    </div>
    <div class="cart-ways">
      <section><h3>Open each product</h3>
        <p class="fine">Works everywhere. Add each one to the cart on the store's page.</p>
        ${linked.length ? `<ul class="cart-links">${linked.map(l => `<li><a href="${esc(l.url)}" target="_blank" rel="noopener"
          data-cart-open="${esc(l.key)}">${esc(l.product)} <span aria-hidden="true">↗</span></a><span>${esc(qtyLabel(l))}</span></li>`).join("")}</ul>`
          : `<p class="fine">This store gave no product pages for these.</p>`}</section>
      <section><h3>Fill the cart in one go</h3>${extensionWay(b.store)}</section>
      <section id="cartAsk"><h3>One tap, also on your phone</h3>
        <p class="fine">That needs ${esc(eshopName(b.store))} to work with pantryrun. Would you use it?</p>
        <span class="btns"><button type="button" class="btn quiet" data-cart-answer="yes">Yes, I'd use it</button>
          <button type="button" class="link" data-cart-answer="no">Not really</button></span></section>
      ${deliveryAsk()}
    </div>
    <div class="sh-bottom"><button class="btn dark" value="close" type="submit">Done</button></div>`;
  sheetForm.onchange = null;
  sheetForm.onclick = e => {
    const open = e.target.closest("[data-cart-open]");
    if (open) { logEvent("open_product", { store: b.store, key: open.dataset.cartOpen, from: "cart", result_id: data.result_id }); return; }
    if (e.target.closest("#getExtension")) { logEvent("extension_download", data); return; }
    const delivery = e.target.closest("[data-delivery]");
    if (delivery) { answerDelivery(delivery, "sheet"); return; }
    const answer = e.target.closest("[data-cart-answer]");
    if (answer) {
      logEvent("cart_interest", { store: b.store, wants: answer.dataset.cartAnswer === "yes", result_id: data.result_id });
      $("#cartAsk", sheetForm).innerHTML = `<h3>One tap, also on your phone</h3><p class="fine">${answer.dataset.cartAnswer === "yes"
        ? "Thanks. Every yes helps us ask the stores." : "Thanks for saying."}</p>`;
    }
  };
  sheet.onclose = null;
  sheet.setAttribute("aria-labelledby", "sheetTitle");
  sheet.returnValue = "";
  sheet.showModal();
}

// "Order online at Rimi": with the extension the cart fills at once (said in note), else the sheet of ways.
export function sendToCart(b, note) {
  const items = cartItems(b);
  const data = { store: b.store, items: items.length, lines: b.lines.length, result_id: state.result?.result_id ?? null };
  if (b.store === "rimi" && extension() && items.length) { fill(b, items, data, note); return; }
  logEvent("cart_click", data);
  note.innerHTML = `<p>Stores don't let other sites fill their cart yet. Here's what works today.</p>`;
  ways(b, data);
}

after.addEventListener("click", e => {
  const delivery = e.target.closest("[data-delivery]");
  if (delivery) answerDelivery(delivery, "receipt");
});
