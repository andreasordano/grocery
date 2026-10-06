// Choosing another product for a receipt line, and the preferences that come from it:
// the product to use at this store, and words to look for at the others ("Alma", "2,5%").
// Both open in the sheet dialog; onChange runs when the preferences changed, to price again.
import { $, sheet, sheetForm } from "./dom.js";
import { num, cap, esc, fold } from "./format.js";
import { state } from "./state.js";
import { storage } from "./storage.js";
import { logEvent } from "./api.js";
import { lineAmount } from "./receipt.js";

const matches = (product, words) => words.every(w => fold(product).includes(fold(w)));

// Words from a product name that could describe a preference: brand, type, fat %.
// Pack sizes and the ingredient's own name are left out.
function nameWords(product, label) {
  const skip = new Set(fold(label).split(/\s+/));
  const seen = new Set();
  return product.split(/[\s,()/]+/)
    .map(w => w.replace(/^[.\-]+|[.\-]+$/g, ""))
    .filter(w => w.length >= 3 || /%/.test(w))
    .filter(w => !/^\d+([.,]\d+)?(g|kg|ml|l|cl|tk|x\d+.*)?$/i.test(w) && !/^\d+x\d+/i.test(w))
    .filter(w => !skip.has(fold(w)))
    .filter(w => { const k = fold(w); if (seen.has(k)) return false; seen.add(k); return true; })
    .slice(0, 6)
    .map(w => /%/.test(w) ? w : w.toLowerCase());
}

// Show the sheet once its content (with its #sheetTitle heading) is in place.
function openSheet() {
  sheet.setAttribute("aria-labelledby", "sheetTitle");
  sheet.returnValue = "";
  sheet.showModal();
}

function savePrefs(key, change) {
  storage.set("pantryrun.prefs", state.prefs);
  logEvent("preference", { key, change, pref: state.prefs[key] || null });
}

// The products this store has for one line of the receipt.
export function chooseProduct(key, onChange) {
  const res = state.result;
  const b = res.baskets.find(x => x.store === state.view);
  const l = b.lines.find(x => x.key === key);
  const old = state.prefs[key] || {};
  const others = res.baskets.filter(x => x.store !== b.store)
    .map(x => ({ store: x.store, line: x.lines.find(y => y.key === key) }));
  let chosen = l.product;
  let words = [...(old.words || [])];
  const photos = l.options.some(o => o.image);

  // What the other stores will use, given the picked product and the words chosen.
  function cross() {
    const differs = chosen !== l.options[0].product || words.length;
    if (!differs) return `<div class="cross"><p class="fine">The other stores keep their cheapest ${esc(l.label.toLowerCase())}.</p></div>`;
    const suggestions = [...new Set([...words, ...nameWords(chosen, l.label)])];
    const rows = others.map(o => {
      if (!o.line) return `<li><b>${esc(cap(o.store))}:</b> doesn't sell it</li>`;
      if (!words.length) return `<li><b>${esc(cap(o.store))}:</b> keeps the cheapest, ${esc(o.line.options[0].product)}</li>`;
      const hit = o.line.options.find(x => matches(x.product, words));
      return hit
        ? `<li><b>${esc(cap(o.store))}:</b> ${esc(hit.product)}, ${num.format(hit.cost)} €</li>`
        : `<li><b>${esc(cap(o.store))}:</b> nothing matches, so the cheapest stays</li>`;
    }).join("");
    return `<div class="cross">
      <h3>At the other stores, look for</h3>
      <div class="chips">${suggestions.map(w => `<button type="button" data-word="${esc(w)}" aria-pressed="${words.some(x => fold(x) === fold(w))}">${esc(w)}</button>`).join("")}</div>
      <ul class="preview">${rows}</ul>
    </div>`;
  }

  sheetForm.innerHTML = `
    <div class="sh-top">
      <h2 id="sheetTitle">${esc(l.label)}</h2>
      <p>${esc(cap(lineAmount(l) ? lineAmount(l) + " at " : "At "))}${esc(cap(b.store))}. Pick the one you want.</p>
    </div>
    <ul class="opts">${l.options.map((o, i) => `
      <li><label><input type="radio" name="opt" value="${i}" ${o.product === chosen ? "checked autofocus" : ""}>
        <span class="o">${photos ? `<span class="thumb">${o.image ? `<img src="${esc(o.image)}" alt="" loading="lazy" referrerpolicy="no-referrer">` : ""}</span>` : ""}
          <span>${esc(o.product)}${o.deal ? ` <span class="fine">${esc(o.deal)}</span>` : ""}${o.shelf ? `<span class="o-shelf">${esc(o.shelf.toLowerCase())}</span>` : ""}</span></span>
        <span class="pc">${o.regular_cost && o.regular_cost > o.cost ? `<s>${num.format(o.regular_cost)}</s>` : ""}${num.format(o.cost)}</span></label></li>`).join("")}
    </ul>
    <div id="cross">${cross()}</div>
    <div class="sh-bottom">
      <button class="link" value="reset" type="submit">Back to cheapest</button>
      <span class="sh-buttons">
        <button class="btn quiet" value="cancel" type="submit">Cancel</button>
        <button class="btn dark" value="apply" type="submit">Done</button>
      </span>
    </div>`;

  sheetForm.onchange = e => {
    if (e.target.name !== "opt") return;
    chosen = l.options[+e.target.value].product;
    words = words.filter(w => matches(chosen, [w]));  // drop words the new pick doesn't have
    $("#cross", sheetForm).innerHTML = cross();
  };
  sheetForm.onclick = e => {
    const chip = e.target.closest("[data-word]");
    if (!chip) return;
    const w = chip.dataset.word;
    words = words.some(x => fold(x) === fold(w)) ? words.filter(x => fold(x) !== fold(w)) : [...words, w];
    $("#cross", sheetForm).innerHTML = cross();
  };

  sheet.onclose = () => {
    const action = sheet.returnValue;
    if (action !== "apply" && action !== "reset") return;
    const before = JSON.stringify(state.prefs[key] || {});
    if (action === "reset") {
      delete state.prefs[key];
    } else {
      const next = { label: l.label, words, products: { ...(old.products || {}) } };
      if (chosen !== l.options[0].product) next.products[b.store] = chosen;
      else delete next.products[b.store];
      if (!next.words.length && !Object.keys(next.products).length) delete state.prefs[key];
      else state.prefs[key] = next;
    }
    if (JSON.stringify(state.prefs[key] || {}) === before) return;
    savePrefs(key, action);
    onChange();
  };
  openSheet();
}

// ── saved preferences: what they are, and removing them ──

function prefLabel(key) {
  return state.prefs[key]?.label || (key.startsWith("text:") ? key.slice(5) : cap(key.replace(/_/g, " ")));
}

function describePref(p) {
  const parts = [];
  if (p.words?.length) parts.push(`In every store: products with “${p.words.join("”, “")}”`);
  for (const [s, prod] of Object.entries(p.products || {})) parts.push(`At ${cap(s)}: ${prod}`);
  return parts;
}

export function editPreferences(onChange) {
  let changed = false;
  const draw = () => {
    const keys = Object.keys(state.prefs);
    sheetForm.innerHTML = `
      <div class="sh-top">
        <h2 id="sheetTitle">Your preferences</h2>
        <p>${keys.length ? "These replace the cheapest product when they match." : "No preferences saved. Tap an item on the receipt to pick another product."}</p>
      </div>
      ${keys.length ? `<ul class="prefs">${keys.map(k => `<li>
        <div><b>${esc(prefLabel(k))}</b>${describePref(state.prefs[k]).map(t => `<p>${esc(t)}</p>`).join("")}</div>
        <button class="btn quiet" type="button" data-remove-pref="${esc(k)}">Remove</button></li>`).join("")}</ul>` : ""}
      <div class="sh-bottom">
        ${keys.length > 1 ? `<button class="link" type="button" id="removeAll">Remove all</button>` : ""}
        <button class="btn dark" value="close" type="submit">Done</button>
      </div>`;
  };
  draw();
  sheetForm.onchange = null;
  sheetForm.onclick = e => {
    const one = e.target.closest("[data-remove-pref]");
    if (one) { delete state.prefs[one.dataset.removePref]; savePrefs(one.dataset.removePref, "remove"); changed = true; draw(); }
    if (e.target.closest("#removeAll")) {
      for (const k of Object.keys(state.prefs)) { delete state.prefs[k]; savePrefs(k, "remove_all"); }
      changed = true; draw();
    }
  };
  sheet.onclose = () => { if (changed && state.result) onChange(); };
  openSheet();
}
