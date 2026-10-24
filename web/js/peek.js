// A quick look at a receipt line's product: its photo, name, price and a link to it in the e-shop.
// Tap the line's photo to open it; with a mouse, resting on the line opens it too.
// It's a popover (#peek): a tap outside or Escape closes it. On phones it sits at the bottom.
import { $, feed } from "./dom.js";
import { num, cap, esc } from "./format.js";
import { state } from "./state.js";
import { logEvent } from "./api.js";
import { lineAmount, answered } from "./receipt.js";
import { chooseProduct } from "./products.js";

const peek = $("#peek");
const canHover = matchMedia("(hover: hover) and (pointer: fine)");
const phone = matchMedia("(max-width: 900px)");
const OPEN_DELAY = 350, CLOSE_DELAY = 200;  // ms: moving the mouse down the receipt shouldn't flash it

let shownKey = null, closedKey = null, closedAt = 0;
let openTimer, closeTimer;
let onChange = () => {};

const lineFor = key => answered(state.result).find(b => b.store === state.view)?.lines.find(l => l.key === key);
const percentOff = (regular, cost) => Math.round((1 - cost / regular) * 100);

function draw(l) {
  const onSale = l.regular_cost && l.regular_cost > l.cost;
  const amt = lineAmount(l);
  // "2 × 1.99 €", "0.8 kg × 3.99 €/kg"; a single pack says nothing the price doesn't
  const how = l.how && !/^1 × /.test(l.how) ? l.how : "";
  peek.innerHTML = `
    ${l.image ? `<div class="pk-photo"><img src="${esc(l.image)}" alt="" referrerpolicy="no-referrer"></div>` : ""}
    <div class="pk-body">
      <p class="pk-for">${esc(l.label)}${amt ? ` · ${esc(amt)}` : ""} at ${esc(cap(state.view))}</p>
      <h3 class="pk-name">${esc(l.product)}</h3>
      ${l.shelf ? `<p class="pk-shelf">${esc(l.shelf.toLowerCase())}</p>` : ""}
      <p class="pk-price">${onSale ? `<s>${num.format(l.regular_cost)}</s>` : ""}${num.format(l.cost)} €${onSale
        ? `<span class="r-off">−${percentOff(l.regular_cost, l.cost)}%</span>` : ""}</p>
      ${how ? `<p class="pk-how">${esc(how)}</p>` : ""}
      <div class="pk-actions">
        ${l.url ? `<a class="btn dark" href="${esc(l.url)}" target="_blank" rel="noopener" id="pkOpen">Open in ${esc(cap(state.view))} <span aria-hidden="true">↗</span></a>` : ""}
        <button type="button" class="link" id="pkChoose">Choose another</button>
      </div>
    </div>`;
  $("#pkOpen", peek)?.addEventListener("click", () => logOpen(l, "quick_view"));
  $("#pkChoose", peek).onclick = () => { close(); chooseProduct(l.key, onChange); };
}

export function logOpen(l, from) {
  logEvent("open_product", { store: state.view, key: l.key, product: l.product, from, result_id: state.result?.result_id ?? null });
}

// Beside the line, outside the receipt (on its left, where the dinners are); below it when there's no room.
function place(anchor) {
  peek.style.left = peek.style.top = "";
  if (phone.matches) return;  // CSS puts it at the bottom of the screen
  const a = anchor.getBoundingClientRect(), paper = feed.getBoundingClientRect();
  const w = peek.offsetWidth, h = peek.offsetHeight, gap = 14;
  let left = paper.left - w - gap, top = a.top + a.height / 2 - h / 2;
  if (left < gap) { left = a.left; top = a.bottom + 6; }
  peek.style.left = `${Math.max(gap, Math.min(left, innerWidth - w - gap))}px`;
  peek.style.top = `${Math.max(gap, Math.min(top, innerHeight - h - gap))}px`;
}

function open(row) {
  const key = row.dataset.key, l = lineFor(key);
  if (!l) return;
  clearTimeout(closeTimer);
  if (shownKey !== key) {
    draw(l);
    if (!peek.matches(":popover-open")) peek.showPopover();
    place(row);
    shownKey = key;
  }
}

function close() {
  clearTimeout(openTimer);
  if (peek.matches(":popover-open")) peek.hidePopover();
}

peek.addEventListener("toggle", e => {
  if (e.newState === "closed") { closedKey = shownKey; closedAt = performance.now(); shownKey = null; }
});

// Tapping the photo: open, or close when it's already open. The tap outside the popover has
// already closed it (light dismiss) by the time the click arrives, so a just-closed one stays closed.
function toggle(row) {
  if (closedKey === row.dataset.key && performance.now() - closedAt < 300) return;
  shownKey === row.dataset.key ? close() : open(row);
}

// Called once: what to do after another product was chosen from the quick view.
export function bindPeek(changed) {
  onChange = changed;
  feed.addEventListener("click", e => {
    const photo = e.target.closest(".r-photo");
    if (!photo) return;
    e.stopPropagation();  // not a tap on the line: don't open the chooser
    const row = photo.closest("[data-key]");
    if (shownKey !== row.dataset.key) logEvent("quick_view", { store: state.view, key: row.dataset.key, result_id: state.result?.result_id ?? null });
    toggle(row);
  }, true);

  // With a mouse: rest on a line to see its product; leave it (and the popover) to close it.
  feed.addEventListener("mouseover", e => {
    if (!canHover.matches) return;
    const row = e.target.closest(".r-items [data-key]");
    if (!row) return;
    clearTimeout(closeTimer);
    clearTimeout(openTimer);
    openTimer = setTimeout(() => open(row), shownKey ? 0 : OPEN_DELAY);  // already looking: follow the mouse
  });
  const leave = e => {
    if (!canHover.matches || peek.contains(e.relatedTarget) || e.relatedTarget?.closest?.(".r-items [data-key]")) return;
    clearTimeout(openTimer);
    closeTimer = setTimeout(close, CLOSE_DELAY);
  };
  feed.addEventListener("mouseout", leave);
  peek.addEventListener("mouseout", leave);
  peek.addEventListener("mouseover", () => clearTimeout(closeTimer));
}
