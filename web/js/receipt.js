// Drawing the receipt: waiting, printing, failed, and the answer for one store,
// plus what you can do under it (go, not for me, wrong product, send the dinner).
import { $, feed, after, reduceMotion } from "./dom.js";
import { euro, num, cap, esc, amount, fold } from "./format.js";
import { state } from "./state.js";
import { logEvent } from "./api.js";
import { shareDinner } from "./share.js";

function print(html, animate) {
  feed.innerHTML = `<div class="receipt">${html}</div>`;
  if (animate && !reduceMotion()) feed.firstElementChild.classList.add("printing");
}

// On phones the receipt is below the screen: scroll to it when an answer prints.
export function reveal() {
  const top = $(".printer").getBoundingClientRect().top;
  if (top > innerHeight * 0.55) scrollTo({ top: scrollY + top - 70, behavior: reduceMotion() ? "auto" : "smooth" });
}

// Nothing to price yet: a short receipt that says what to do.
export function idle(title, text) {
  state.result = null;
  print(`<div class="waiting"><strong>${esc(title)}</strong>${esc(text)}</div>`, false);
  after.innerHTML = "";
}

export function printing(text) {
  print(`<div class="waiting"><strong>${esc(text)}</strong>Comparing prices<span class="dots"><i>.</i><i>.</i><i>.</i></span></div>`, false);
  after.innerHTML = "";
  reveal();
}

export function failed(retry) {
  feed.classList.remove("busy");
  print(`<div class="waiting"><strong>The stores didn't answer</strong>Check your connection, then try again.</div>`, false);
  after.innerHTML = `<button class="btn quiet wide" type="button" id="retry">Try again</button>`;
  $("#retry").onclick = () => retry();
}

// What to show next to the item name. Recipe lines say how much the recipe needs ("need 4 tk");
// the pack comes from the product name. List items have no amount of their own, except loose
// goods priced by weight, where the price only makes sense with the weight we assumed.
export function lineAmount(l) {
  if (l.asked) return l.asked;  // typed with the item: "600 g", "2 packs"
  if (l.need == null) return "";
  if (!l.extra) return `need ${amount(l.need, l.unit)}`;
  return l.packs == null ? amount(l.need, l.unit) : "";
}

const shortDate = iso => { const [, m, d] = iso.split("-"); return `${+d}.${m}`; };
const percentOff = (regular, cost) => Math.round((1 - cost / regular) * 100);

// The store shelf says what an unclear product is ("… NATTY ORIGINAL, 333g · magusad hoidised");
// left out when it only repeats the item ("banaan · banaan").
const shelfNote = l => l.shelf && !fold(l.shelf).includes(fold(l.label).slice(0, 4)) ? l.shelf.toLowerCase() : "";

function line(l) {
  const tag = l.substitute ? "swap" : (l.pinned || l.preferred) ? "your pick" : "";
  const amt = lineAmount(l);
  const onSale = l.regular_cost && l.regular_cost > l.cost;
  const off = onSale ? `<span class="r-off">−${percentOff(l.regular_cost, l.cost)}%${l.deal_until ? ` until ${shortDate(l.deal_until)}` : ""}</span>` : "";
  const notes = [
    l.card_cost && l.card_cost < l.cost ? `${num.format(l.card_cost)} with a loyalty card` : "",
    l.deal || "",
  ].filter(Boolean);
  return `<li><button type="button" class="r-line" data-key="${esc(l.key)}" aria-label="Choose another ${esc(l.label)}">
    <span class="n">${esc(l.label)}${amt ? ` <span class="amt">${esc(amt)}</span>` : ""}${off}${tag ? `<span class="r-tag">${tag}</span>` : ""}</span>
    <span class="c">${onSale ? `<s>${num.format(l.regular_cost)}</s>` : ""}${num.format(l.cost)}</span>
    <span class="p">${esc(l.product)}${shelfNote(l) ? `<span class="shelf"> · ${esc(shelfNote(l))}</span>` : ""}</span>
    ${notes.length ? `<span class="d">${esc(notes.join(". "))}</span>` : ""}</button></li>`;
}

// Items the recipe assumes you have. Tapping one adds it to this trip.
function pantryNote(res) {
  const notAdded = (res.recipe?.pantry || []).filter(p => !state.extras.some(e => e.toLowerCase() === p.toLowerCase()));
  if (!notAdded.length) return "";
  return `<div class="r-note r-pantry">Have at home: ${notAdded.map(p => `<button type="button" data-pantry="${esc(p)}" aria-label="Add ${esc(p)} to the trip">${esc(p)}</button>`).join(", ")}. Missing one? Tap it to add it.</div>`;
}

function prefsNote(b) {
  const keys = Object.keys(state.prefs);
  if (!keys.length) return "";
  const used = b.lines.filter(l => l.pinned || l.preferred).map(l => l.label);
  const text = used.length ? `Using your preferences for ${used.join(", ")}.` : `You have ${keys.length} saved ${keys.length === 1 ? "preference" : "preferences"}.`;
  return `<div class="r-prefs">${esc(text)} <button type="button" id="editPrefs">Edit preferences</button></div>`;
}

// The receipt for one store of the current answer (the recommended one unless another was tapped).
export function showReceipt(storeName, animate) {
  const res = state.result;
  const best = res.baskets[0];
  const b = res.baskets.find(x => x.store === storeName) || best;
  state.view = b.store;
  const isBest = b.store === best.store;
  const main = b.lines.filter(l => !l.extra), extra = b.lines.filter(l => l.extra);
  const delta = !isBest && (b.missing.length > best.missing.length
    ? `${cap(best.store)} has more of your list`
    : `${euro.format(b.total_price - best.total_price)} more than ${cap(best.store)}`);
  const n = res.items.length;
  const what = res.recipe ? `${res.recipe.name} for ${res.servings}` : `Your list of ${n}`;

  print(`
    <div class="r-center">
      <div class="r-go">${isBest ? "Go to" : "At"}</div>
      <h2 class="r-store">${esc(cap(b.store))}</h2>
      <div class="r-what">${esc(what)}</div>
      ${delta ? `<div class="r-delta">${esc(delta)}</div>` : ""}
    </div>
    <hr class="r-rule">
    <ul class="r-items">${main.map(line).join("")}</ul>
    ${res.recipe && extra.length ? `<div class="r-head">Also</div>` : ""}
    ${extra.length ? `<ul class="r-items">${extra.map(line).join("")}</ul>` : ""}
    ${b.missing.length ? `<div class="r-missing">Not in the e-shop: ${b.missing.map(esc).join(", ")}</div>` : ""}
    <div class="r-hint">Tap an item to choose another.</div>
    <hr class="r-rule">
    <div class="r-total"><span>Total</span><span>${euro.format(b.total_price)}</span></div>
    ${b.savings > 0 ? `<div class="r-save"><span>You save</span><span>${euro.format(b.savings)}</span></div>` : ""}
    ${b.card_savings > 0 ? `<div class="r-card">${euro.format(b.card_savings)} less with a loyalty card</div>` : ""}
    ${pantryNote(res)}
    ${prefsNote(b)}
    ${res.baskets.length > 1 ? `<hr class="r-rule"><div class="r-head">Compare stores</div>
      <ul class="stores">${res.baskets.map(o => `<li><button type="button" data-store="${esc(o.store)}" aria-current="${o.store === b.store}">
        <span class="s">${esc(cap(o.store))}</span><span class="v">${euro.format(o.total_price)}${o.missing.length ? ` (${o.missing.length} missing)` : ""}</span></button></li>`).join("")}</ul>` : ""}
  `, animate);

  after.innerHTML = `
    <div class="actions" id="fb">
      <button class="btn go" type="button" data-fb="accept">I'll go to ${esc(cap(b.store))}</button>
      <button class="btn quiet" type="button" data-fb="reject">Not for me</button>
    </div>
    <div class="small">
      <button class="link" type="button" id="wrong">Wrong product?</button>
      <span class="fine">E-shop prices. In store they can differ a little.</span>
    </div>
    <div id="report"></div>
    ${res.recipe ? `<div class="share"><button class="btn quiet" type="button" id="share">Send this dinner to someone</button>
      <span class="fine" id="shareNote" role="status"></span></div>` : ""}`;
  if (res.recipe) $("#share").onclick = () => shareDinner(res.recipe);

  const feedback = { mission: state.mode, recipe_id: res.recipe?.id ?? null, servings: res.servings, items: res.items,
                     store: b.store, recommended_store: best.store, total_price: b.total_price, result_id: res.id };
  after.querySelectorAll("[data-fb]").forEach(btn => btn.onclick = () => {
    const accepted = btn.dataset.fb === "accept";
    logEvent(btn.dataset.fb, feedback);
    $("#fb").innerHTML = `<p class="thanks">${accepted ? "Have a good trip." : "Thanks. We'll use that to improve."}</p>`;
    if (accepted) feed.firstElementChild.insertAdjacentHTML("beforeend", `<div class="stamp">Going</div>`);
  });
  $("#wrong").onclick = () => {
    $("#report").innerHTML = `<div class="report">
      <select id="wrongItem" aria-label="Which product is wrong">${b.lines.map((l, i) => `<option value="${i}">${esc(l.label)}: ${esc(l.product)}</option>`).join("")}</select>
      <button class="btn quiet" type="button" id="sendReport">Report</button></div>`;
    $("#sendReport").onclick = () => {
      const l = b.lines[+$("#wrongItem").value];
      logEvent("wrong_product", { store: b.store, key: l.key, ingredient: l.ingredient, product: l.product, mission: state.mode, recipe_id: res.recipe?.id ?? null });
      $("#report").innerHTML = `<div class="report"><p class="thanks">Reported. We'll fix it.</p></div>`;
    };
  };
}
