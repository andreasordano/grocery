// Sending the basket to the store's e-shop cart, for people who shop online. Only Rimi, and only
// with pantryrun's browser extension (extension/), which fills the cart in the person's own
// browser. Everywhere else the button asks whether they'd use it, to learn if it's worth building.
import { $, after } from "./dom.js";
import { cap, esc } from "./format.js";
import { state } from "./state.js";
import { logEvent } from "./api.js";

const extension = () => (document.documentElement.dataset.pantryrunCart || "").split(" ").includes("rimi");

// The receipt's products as the cart takes them: the store's product id and how many (or kg).
const cartItems = b => b.lines.filter(l => l.store_id && l.cart_qty)
  .map(l => ({ id: String(l.store_id), qty: +l.cart_qty, name: l.product }));

export const cartButton = b => `<div class="cart" id="cart">
  <button type="button" class="link" id="sendCart" data-store="${esc(b.store)}">Shopping online? Send this to the ${esc(cap(b.store))} cart</button>
</div>`;

function send(b) {
  const items = cartItems(b);
  const data = { store: b.store, items: items.length, lines: b.lines.length, result_id: state.result?.result_id ?? null };
  if (b.store === "rimi" && extension() && items.length) {
    window.postMessage({ source: "pantryrun", type: "fill-cart", store: "rimi", items }, location.origin);
    logEvent("cart_send", { ...data, via: "extension" });
    $("#cart").innerHTML = `<p class="fine">Opening Rimi in a new tab. Your cart fills in a moment${items.length < b.lines.length
      ? `; ${b.lines.length - items.length} ${b.lines.length - items.length === 1 ? "product" : "products"} you'll add by hand` : ""}.</p>`;
    return;
  }
  logEvent("cart_click", data);
  $("#cart").innerHTML = `<div class="cart-ask">
    <p>Filling the ${esc(cap(b.store))} cart for you isn't ready yet. Would you use it?</p>
    <span class="btns"><button type="button" class="btn quiet" data-cart-answer="yes">Yes, I'd use it</button>
      <button type="button" class="link" data-cart-answer="no">Not really</button></span></div>`;
}

after.addEventListener("click", e => {
  const button = e.target.closest("#sendCart");
  if (button) {
    const b = state.result.baskets.find(x => x.store === button.dataset.store);
    if (b) send(b);
    return;
  }
  const answer = e.target.closest("[data-cart-answer]");
  if (answer) {
    logEvent("cart_interest", { store: state.view, wants: answer.dataset.cartAnswer === "yes", result_id: state.result?.result_id ?? null });
    $("#cart").innerHTML = `<p class="fine">${answer.dataset.cartAnswer === "yes" ? "Thanks. That tells us to build it." : "Thanks for saying."}</p>`;
  }
});
