// Drawing the receipt (step 2): waiting, printing, failed, and the answer for one store, with notes under it
// (e-shop prices, wrong product). Then step 3, how you'll get it: in the store, online, or delivered.
// Picking one is what "accept" means; "Not for me" is the reject.
import { $, feed, under, after, reduceMotion } from "./dom.js";
import { euro, num, esc, amount, fold, storeNames, shopName, eshopName, chains } from "./format.js";
import { state } from "./state.js";
import { logEvent } from "./api.js";
import { identity } from "./identity.js";
import { sendToCart, deliveryFollowUp } from "./cart.js";
import { newsletterBox, bindNewsletterBox } from "./newsletter.js";
import { refreshSteps } from "./steps.js";
import { refreshFooter } from "./footer.js";

function print(html, animate) {
  feed.innerHTML = `<div class="receipt">${html}</div>`;
  if (animate && !reduceMotion()) feed.firstElementChild.classList.add("printing");
}

// No answer on the receipt: nothing under it, nothing to choose in step 3.
function empty(status) {
  state.status = status;
  under.innerHTML = after.innerHTML = "";
  refreshSteps();
}

// Nothing to price yet: a short receipt that says what to do.
export function idle(title, text) {
  state.result = null;
  print(`<div class="waiting"><strong>${esc(title)}</strong>${esc(text)}</div>`, false);
  empty("idle");
}

export function printing(text) {
  print(`<div class="waiting"><strong>${esc(text)}</strong>Comparing prices<span class="dots"><i>.</i><i>.</i><i>.</i></span></div>`, false);
  empty("pricing");
}

export function failed(retry) {
  feed.classList.remove("busy");
  print(`<div class="waiting"><strong>The stores didn't answer</strong>Check your connection, then try again.</div>`, false);
  empty("failed");
  under.innerHTML = `<button class="btn quiet wide" type="button" id="retry">Try again</button>`;
  $("#retry").onclick = () => retry();
}

// The stores that answered, best first. A store that didn't answer (status "no_answer") isn't ranked:
// nothing is known about what it sells.
export const answered = res => res.baskets.filter(b => b.status !== "no_answer");

// "Selver didn't answer, prices from Rimi and Barbora"
function downNote(res) {
  const down = res.baskets.filter(b => b.status === "no_answer").map(b => b.store);
  if (!down.length) return "";
  return `<div class="r-note r-down">${esc(storeNames(down))} didn't answer, prices from ${esc(storeNames(answered(res).map(b => b.store)))}</div>`;
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

const X = `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.4" stroke-linecap="round"><path d="M7 7l10 10M17 7 7 17"/></svg>`;
const skipButton = (key, label) => `<button type="button" class="r-x" data-skip="${esc(key)}" data-label="${esc(label)}"
  aria-label="Leave out ${esc(label)}" title="I don't need this">${X}</button>`;

// photos: the store has photos for this receipt, so every line keeps a photo's place (lined up).
// removable: there's more than this one line, so × can take it off.
function line(l, photos, removable) {
  const tag = l.substitute ? "swap" : (l.pinned || l.preferred) ? "your pick" : "";
  const amt = lineAmount(l);
  const onSale = l.regular_cost && l.regular_cost > l.cost;
  const off = onSale ? `<span class="r-off">−${percentOff(l.regular_cost, l.cost)}%${l.deal_until ? ` until ${shortDate(l.deal_until)}` : ""}</span>` : "";
  const notes = [
    l.bought ? `You buy ${amount(l.bought, "g")}, the least the store sells` : "",
    l.card_cost && l.card_cost < l.cost ? `${num.format(l.card_cost)} with a loyalty card` : "",
    l.deal || "",
  ].filter(Boolean);
  const photo = !photos ? "" : l.image
    ? `<button type="button" class="r-photo" aria-label="Look at ${esc(l.product)}"><img src="${esc(l.image)}" alt="" loading="lazy" referrerpolicy="no-referrer"></button>`
    : `<span class="r-photo" aria-hidden="true"></span>`;
  return `<li data-key="${esc(l.key)}">${photo}<button type="button" class="r-line" data-key="${esc(l.key)}" aria-label="Choose another ${esc(l.label)}">
    <span class="n">${esc(l.label)}${amt ? ` <span class="amt">${esc(amt)}</span>` : ""}${off}${tag ? `<span class="r-tag">${tag}</span>` : ""}</span>
    <span class="c">${onSale ? `<s>${num.format(l.regular_cost)}</s>` : ""}${num.format(l.cost)}</span>
    <span class="p">${esc(l.product)}${shelfNote(l) ? `<span class="shelf"> · ${esc(shelfNote(l))}</span>` : ""}</span>
    ${l.for ? `<span class="f">for ${esc(l.for.join(", "))}</span>` : ""}
    ${notes.length ? `<span class="d">${esc(notes.join(". "))}</span>` : ""}</button>${removable ? skipButton(l.key, l.label) : ""}</li>`;
}

// The store that's cheapest for what the dinners use, when it isn't the cheapest to pay (core/catalog._best_value):
// its bigger amounts cost more today, but you keep what's left over.
function valueNote(res, b, stores) {
  const bv = stores.find(o => o.store === res.best_value);
  if (!bv) return "";
  if (b.store === bv.store) {
    const big = b.lines.filter(l => l.used_cost != null && l.used_cost < l.cost - 0.5).map(l => l.label);
    return `<div class="r-note r-value"><span class="bv">★ Best value for what you use</span> What you use is worth ${euro.format(b.used_price)}.
      You pay more today${big.length ? ` because ${esc(big.join(", "))} ${big.length === 1 ? "comes" : "come"} in more than you need` : ""}, and keep the rest.</div>`;
  }
  return `<div class="r-note r-value"><span class="bv">★ Best value for what you use</span> <button type="button" data-store="${esc(bv.store)}">${esc(shopName(bv.store))}</button>:
    ${euro.format(bv.total_price)} today, but what you use is worth ${euro.format(bv.used_price)}. You keep the rest.</div>`;
}

// Fresh things an e-shop lacks are often at a counter in the store: where to look, for the "In the store" way.
const COUNTERS = [
  [["kala", "lõhe", "tursk", "ahven", "forell", "heik", "räim", "kilu", "makrell", "krevet", "tuun", "koha", "lest", "angerjas"], "the fish counter"],
  [["liha", "filee", "hakk", "sea", "veise", "lamba", "kana", "broiler", "kalkun", "part", "ribi", "karbonaad", "vorst", "sink"], "the meat counter"],
  [["petersell", "till", "koriander", "münt", "basiilik", "murulauk", "salat", "spinat", "rukola", "seller", "porru", "ürt"], "the vegetable section"],
];
const counter = label => COUNTERS.find(([words]) => words.some(w => fold(label).includes(fold(w))))?.[1];

// Missing here: still on your list (the receipt is the list in the store), with why (sold out online today, or
// not in this e-shop), where to look in the store for fresh things, and × to leave it out everywhere.
function missingNote(b, removable) {
  if (!b.missing.length) return "";
  return `<div class="r-missing"><div class="r-head">Not in ${esc(eshopName(b.store))}'s e-shop: still on your list</div>
    <ul>${b.missing.map((m, i) => {
      const where = counter(m), soldOut = b.missing_why?.[i]?.sold_out;
      return `<li><span><b>${esc(m)}</b> ${soldOut ? "· sold out online today" : ""}${where
        ? `<span class="r-where">In the store, try ${where}.</span>` : ""}</span>${removable && b.missing_keys?.[i] ? skipButton(b.missing_keys[i], m) : ""}</li>`;
    }).join("")}</ul></div>`;
}

// What was taken off with ×: tap one to put it back.
function skippedNote(res) {
  if (!res.skipped?.length) return "";
  return `<div class="r-note r-pantry r-skipped">Left out: ${res.skipped.map(s => `<button type="button" data-unskip="${esc(s.key)}"
    aria-label="Put ${esc(s.label)} back">${esc(s.label)}</button>`).join(", ")}. Tap one to put it back.</div>`;
}

// Items the recipe assumes you have. Tapping one adds it to the basket.
function pantryNote(res) {
  const notAdded = (res.pantry ?? res.recipe?.pantry ?? []).filter(p => !state.extras.some(e => e.toLowerCase() === p.toLowerCase()));
  if (!notAdded.length) return "";
  return `<div class="r-note r-pantry">Have at home: ${notAdded.map(p => `<button type="button" data-pantry="${esc(p)}" aria-label="Add ${esc(p)} to the basket">${esc(p)}</button>`).join(", ")}. Missing one? Tap it to add it.</div>`;
}

// Said only when a preference changed a product here; how many there are is in the foot.
function prefsNote(b) {
  const used = b.lines.filter(l => l.pinned || l.preferred).map(l => l.label);
  if (!used.length) return "";
  return `<div class="r-prefs">${esc(`Using your preferences for ${used.join(", ")}.`)} <button type="button" data-prefs>Edit preferences</button></div>`;
}

// ── Step 3: how you'll get it ──
const ICONS = {
  store: `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M6 7h12l-1 13H7L6 7z"/><path d="M9 7a3 3 0 0 1 6 0"/></svg>`,
  online: `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M3 4h2l2.4 11h10.2L20 8H6.2"/><circle cx="9" cy="19" r="1.5"/><circle cx="17" cy="19" r="1.5"/></svg>`,
  delivery: `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="6" cy="17" r="2.5"/><circle cx="18" cy="17" r="2.5"/><path d="M8.5 17h7M14 6h3l2 8.5M5 11h7l2 6"/></svg>`,
};

const ways = b => [
  { via: "store", title: "In the store", text: "Take the list with you on your phone." },
  { via: "online", title: `Order online at ${eshopName(b.store)}`, text: `Add these products to your ${eshopName(b.store)} cart.` },
  { via: "delivery", title: "Delivered by Wolt or Bolt", text: "Not possible yet. Tap if you'd use it." },
];

// The way picked for this store's receipt of this answer, if any.
const wayFor = (res, b) => state.way?.result_id === res.result_id && state.way.store === b.store ? state.way.via : null;

function getIt(res, b) {
  const way = wayFor(res, b);
  return `<h2 class="card-title" id="getTitle"><span class="num" aria-hidden="true">3</span>How will you get it?</h2>
    <p class="card-sub">${esc(shopName(b.store))}, ${euro.format(b.total_price)}. Your list works either way.</p>
    <div class="ways" role="group" aria-labelledby="getTitle">${ways(b).map(w => `
      <button type="button" class="way" data-way="${w.via}" aria-pressed="${w.via === way}">
        <span class="way-icon ${w.via}" aria-hidden="true">${ICONS[w.via]}</span>
        <span class="way-text"><b>${esc(w.title)}</b><span>${esc(w.text)}</span></span></button>`).join("")}
    </div>
    <div class="way-note" id="wayNote" role="status"></div>
    <div class="get-news">${way ? newsletterBox("get_it") : ""}</div>
    <p class="way-foot">${way ? "" : `<button class="link" type="button" data-fb="reject">Not for me</button>`}
      <span class="fine">In the store, prices can differ a little.</span></p>`;
}

// The receipt for one store of the current answer (the recommended one unless another was tapped).
export function showReceipt(storeName, animate) {
  const res = state.result;
  const stores = answered(res);
  const best = stores[0];
  const b = stores.find(x => x.store === storeName) || best;
  state.view = b.store;
  const isBest = b.store === best.store;
  const main = b.lines.filter(l => !l.extra), extra = b.lines.filter(l => l.extra);
  const photos = b.lines.some(l => l.image);
  const removable = b.lines.length + b.missing.length > 1;  // the last thing stays: nothing would be left to price
  const items = lines => `<ul class="r-items${photos ? " photos" : ""}">${lines.map(l => line(l, photos, removable)).join("")}</ul>`;
  const delta = !isBest && (b.missing.length > best.missing.length
    ? `${shopName(best.store)} has more of your list`
    : `${euro.format(b.total_price - best.total_price)} more than ${shopName(best.store)}`);
  const n = res.items.length;
  const dinners = res.dinners ?? (res.recipe ? [res.recipe] : []);
  const what = dinners.length > 1 ? `${dinners.length} dinners for ${res.servings}`
    : res.recipe ? `${res.recipe.name} for ${res.servings}` : `Your list of ${n}`;

  print(`
    <div class="r-center">
      <div class="r-go">${isBest ? "Cheapest at" : "At"}</div>
      <h2 class="r-store">${esc(shopName(b.store))}</h2>
      ${eshopName(b.store) !== shopName(b.store)
        ? `<div class="r-what">Prices from ${esc(eshopName(b.store))}, ${esc(shopName(b.store))}'s e-shop</div>` : ""}
      <div class="r-what">${esc(what)}</div>
      ${delta ? `<div class="r-delta">${esc(delta)}</div>` : ""}
      ${chains()[identity.usualStore] === shopName(b.store) ? `<div class="r-usual">Your usual store</div>` : ""}
    </div>
    ${downNote(res)}
    <hr class="r-rule">
    ${items(main)}
    ${dinners.length && extra.length ? `<div class="r-head">Also</div>` : ""}
    ${extra.length ? items(extra) : ""}
    ${missingNote(b, removable)}
    <div class="r-hint">${photos ? "Tap a photo for a closer look, an item to choose another" : "Tap an item to choose another"}${removable
      ? ", × if you don't need it." : "."}</div>
    <hr class="r-rule">
    <div class="r-total"><span>Total</span><span>${euro.format(b.total_price)}</span></div>
    ${b.savings > 0 ? `<div class="r-save"><span>You save</span><span>${euro.format(b.savings)}</span></div>` : ""}
    ${b.card_savings > 0 ? `<div class="r-card">${euro.format(b.card_savings)} less with a loyalty card</div>` : ""}
    ${valueNote(res, b, stores)}
    ${skippedNote(res)}
    ${pantryNote(res)}
    ${prefsNote(b)}
    ${stores.length > 1 ? `<hr class="r-rule"><div class="r-head">Compare stores</div>
      <ul class="stores">${stores.map(o => `<li><button type="button" data-store="${esc(o.store)}" aria-current="${o.store === b.store}">
        <span class="s">${esc(shopName(o.store))}</span><span class="v">${euro.format(o.total_price)}${o.missing.length ? ` (${o.missing.length} missing)`
          : stores.some(x => x.missing.length) ? " · has everything" : ""}</span>${o.store === res.best_value
          ? `<span class="bv">★ Best value for what you use</span>` : ""}</button></li>`).join("")}</ul>` : ""}
  `, animate);
  const stamp = () => { if (!$(".stamp", feed)) feed.firstElementChild.insertAdjacentHTML("beforeend", `<div class="stamp">Going</div>`); };
  if (wayFor(res, b) === "store") stamp();  // drawn again, e.g. after the usual store changed

  state.status = "answer";
  under.innerHTML = `<p class="fine"><span>${eshopName(b.store) === shopName(b.store)  // else the receipt says whose e-shop
      ? `Prices from the ${esc(eshopName(b.store))} e-shop.` : "E-shop prices."}</span>
      <button class="link" type="button" id="wrong">Wrong product?</button></p>
    <div id="report"></div>`;
  after.innerHTML = getIt(res, b);
  refreshSteps();
  refreshFooter();

  const feedback = { usual_store: identity.usualStore === "skip" ? null : identity.usualStore ?? null, mission: dinners.length > 1 ? "dinners" : state.mode, recipe_id: res.recipe?.id ?? null,
                     recipe_ids: dinners.map(d => d.id), servings: res.servings, items: res.items,
                     store: b.store, recommended_store: best.store, total_price: b.total_price, result_id: res.result_id };
  // One accept per store's receipt of an answer, with the way picked first; picking another way after that
  // is a way_change, so counting accepts (and store switches) stays as it was with "I'll go to <store>".
  const pickWay = via => {
    const before = wayFor(res, b);
    if (via === before && via !== "online") return;  // online again: open the ways to fill the cart again
    state.way = { result_id: res.result_id, store: b.store, via };
    if (!before) logEvent("accept", { ...feedback, via });
    else if (via !== before) logEvent("way_change", { via, from: before, store: b.store, result_id: res.result_id });
    after.innerHTML = getIt(res, b);
    bindNewsletterBox("get_it");
    const note = $("#wayNote");
    if (via === "store") {
      note.innerHTML = `<p>Have a good shop. Keep this page open: your list is the receipt.</p>
        <span class="btns"><button class="btn quiet see-list" type="button" data-go="2">See the list</button></span>`;
      stamp();
    } else {
      $(".stamp", feed)?.remove();
      if (via === "online") sendToCart(b, note);
      else note.innerHTML = deliveryFollowUp();
    }
    refreshSteps();
  };
  after.onclick = e => {
    const way = e.target.closest("[data-way]");
    if (way) { pickWay(way.dataset.way); return; }
    if (e.target.closest("[data-fb=reject]")) {
      logEvent("reject", feedback);
      $(".ways", after).remove();
      $(".way-foot", after).innerHTML = `<span class="thanks">Thanks. We'll use that to improve.</span>`;
    }
  };
  $("#wrong").onclick = () => {
    $("#report").innerHTML = `<div class="report">
      <select id="wrongItem" aria-label="Which product is wrong">${b.lines.map((l, i) => `<option value="${i}">${esc(l.label)}: ${esc(l.product)}</option>`).join("")}</select>
      <button class="btn quiet" type="button" id="sendReport">Report</button></div>`;
    $("#sendReport").onclick = () => {
      const l = b.lines[+$("#wrongItem").value];
      logEvent("wrong_product", { store: b.store, key: l.key, ingredient: l.ingredient, product: l.product, mission: state.mode, recipe_id: res.recipe?.id ?? null, result_id: res.result_id });
      $("#report").innerHTML = `<div class="report"><p class="thanks">Reported. We'll fix it.</p></div>`;
    };
  };
}
