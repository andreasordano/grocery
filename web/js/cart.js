// Sending the basket to the store's e-shop, for people who shop online. Stores don't let another site
// fill their cart, so there are three ways, shown in the sheet: open each product, pantryrun's browser
// extension (extension/, Rimi only, computers only), or one tap once a store works with us (would you
// use it?). With the extension on the Rimi receipt, "Send" fills the cart straight away.
import { $, after, sheet, sheetForm } from "./dom.js";
import { cap, esc, num } from "./format.js";
import { state } from "./state.js";
import { logEvent } from "./api.js";

const extension = () => (document.documentElement.dataset.pantryrunCart || "").split(" ").includes("rimi");
const phone = () => matchMedia("(pointer: coarse)").matches;

// The receipt's products as the cart takes them: the store's product id and how many (or kg).
const cartItems = b => b.lines.filter(l => l.store_id && l.cart_qty)
  .map(l => ({ id: String(l.store_id), qty: +l.cart_qty, name: l.product }));

const qtyLabel = l => l.packs ? `${l.packs} ×` : l.cart_qty ? `${num.format(l.cart_qty)} kg` : "";

export const cartButton = b => `<div class="cart" id="cart">
  <button type="button" class="link" id="sendCart" data-store="${esc(b.store)}">Shopping online? Send this to the ${esc(cap(b.store))} cart</button>
</div>`;

function fill(b, items, data) {
  window.postMessage({ source: "pantryrun", type: "fill-cart", store: "rimi", items }, location.origin);
  logEvent("cart_send", { ...data, via: "extension" });
  const byHand = b.lines.length - items.length;
  $("#cart").innerHTML = `<p class="fine">Opening Rimi in a new tab. Your cart fills in a moment${byHand
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
      <h2 id="sheetTitle">Shopping online at ${esc(cap(b.store))}?</h2>
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
        <p class="fine">That needs ${esc(cap(b.store))} to work with pantryrun. Would you use it?</p>
        <span class="btns"><button type="button" class="btn quiet" data-cart-answer="yes">Yes, I'd use it</button>
          <button type="button" class="link" data-cart-answer="no">Not really</button></span></section>
    </div>
    <div class="sh-bottom"><button class="btn dark" value="close" type="submit">Done</button></div>`;
  sheetForm.onchange = null;
  sheetForm.onclick = e => {
    const open = e.target.closest("[data-cart-open]");
    if (open) { logEvent("open_product", { store: b.store, key: open.dataset.cartOpen, from: "cart", result_id: data.result_id }); return; }
    if (e.target.closest("#getExtension")) { logEvent("extension_download", data); return; }
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

after.addEventListener("click", e => {
  const button = e.target.closest("#sendCart");
  if (!button) return;
  const b = state.result.baskets.find(x => x.store === button.dataset.store);
  if (!b) return;
  const items = cartItems(b);
  const data = { store: b.store, items: items.length, lines: b.lines.length, result_id: state.result?.result_id ?? null };
  if (b.store === "rimi" && extension() && items.length) { fill(b, items, data); return; }
  logEvent("cart_click", data);
  ways(b, data);
});
