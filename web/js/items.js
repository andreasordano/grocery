// Lists of things to buy, used by all three screens: the field that adds items (with suggestions),
// and the items themselves (tap one to change it, × to remove it).
// Each screen passes its own list and what to do after it changes.
import { $ } from "./dom.js";
import { esc, splitItems } from "./format.js";
import { logEvent } from "./api.js";
import { state } from "./state.js";
import { loadVocab, suggest, splitQty } from "./suggest.js";

// An item on a list; tapping it turns it into a text field, e.g. to add an amount.
export const itemButton = (it, i) => `<button type="button" class="it" data-edit="${i}" aria-label="Change ${esc(it)}">${esc(it)}</button>`;

// The add form (#add with #item): typed items, comma-separated, or a picked suggestion.
export function bindAdd(list, onChange) {
  const form = $("#add"), input = $("#item");
  const box = document.createElement("ul");
  box.className = "suggest"; box.id = "suggest"; box.setAttribute("role", "listbox"); box.hidden = true;
  form.append(box);
  Object.entries({ role: "combobox", "aria-autocomplete": "list", "aria-controls": "suggest", "aria-expanded": "false" })
    .forEach(([k, v]) => input.setAttribute(k, v));
  let shown = [], active = -1;

  function add(text, via, typed) {
    const added = splitItems(text).filter(it => !list.includes(it));
    list.push(...added);
    if (added.length) logEvent("item_added", { items: added, via, typed, mode: state.mode });
    onChange();
    $("#item").focus();  // the form was redrawn
  }
  function show(words) {
    shown = words; active = -1;
    box.innerHTML = words.map((v, i) => `<li role="option" id="sg${i}" aria-selected="false" data-i="${i}">
      <span>${esc(v.w)}</span>${v.s ? `<span class="s-shelf">${esc(v.s.toLowerCase())}</span>` : ""}</li>`).join("");
    box.hidden = !words.length;
    input.setAttribute("aria-expanded", String(!box.hidden));
    input.removeAttribute("aria-activedescendant");
  }
  function move(step) {
    if (!shown.length) return;
    active = (active + step + shown.length + 2) % (shown.length + 1) - 1;  // -1 = back to what was typed
    box.querySelectorAll("li").forEach((li, i) => li.setAttribute("aria-selected", i === active));
    active < 0 ? input.removeAttribute("aria-activedescendant") : input.setAttribute("aria-activedescendant", `sg${active}`);
  }
  function pick(i) {
    const parts = input.value.split(",");
    const typed = parts.pop().trim();
    const { lead, trail } = splitQty(typed);  // keep "600g" in "600g pap" → "600g paprika"
    add([...parts, lead + shown[i].w + trail].join(","), "suggestion", typed);
  }

  input.addEventListener("focus", loadVocab, { once: true });
  input.addEventListener("input", () => show(suggest(splitQty(input.value.split(",").pop().trim()).name)));
  input.addEventListener("keydown", e => {
    if (box.hidden) return;
    if (e.key === "ArrowDown" || e.key === "ArrowUp") { e.preventDefault(); move(e.key === "ArrowDown" ? 1 : -1); }
    else if (e.key === "Enter" && active >= 0) { e.preventDefault(); pick(active); }
    else if (e.key === "Escape") show([]);
  });
  input.addEventListener("blur", () => setTimeout(() => show([]), 150));
  box.addEventListener("pointerdown", e => e.preventDefault());  // keep focus in the input
  box.addEventListener("click", e => { const li = e.target.closest("li"); if (li) pick(+li.dataset.i); });
  form.addEventListener("submit", e => { e.preventDefault(); add(input.value, "typed"); });
}

// A tap on an item's text or its ×. Returns true when it was one.
export function itemClick(e, list, onChange) {
  const remove = e.target.closest("[data-remove]");
  if (remove) {
    list.splice(+remove.dataset.remove, 1);
    onChange();
    return true;
  }
  const edit = e.target.closest("[data-edit]");
  if (edit) {
    editItem(edit, list, onChange);
    return true;
  }
  return false;
}

// The item becomes a text field: Enter or leaving it keeps the change, Escape drops it, emptying it removes the item.
function editItem(button, list, onChange) {
  const i = +button.dataset.edit;
  const field = document.createElement("input");
  field.className = "edit"; field.value = list[i]; field.setAttribute("aria-label", "Change item");
  button.replaceWith(field);
  field.focus(); field.select();
  let done = false;
  const finish = keep => {
    if (done) return;
    done = true;
    const text = field.value.trim().replace(/\s+/g, " ");
    if (keep && text !== list[i]) {
      if (text) list[i] = text; else list.splice(i, 1);
      logEvent("item_changed", { mode: state.mode, to: text || null });
    }
    onChange();
  };
  field.addEventListener("keydown", e => {
    if (e.key === "Enter") { e.preventDefault(); finish(true); }
    if (e.key === "Escape") { e.preventDefault(); finish(false); }
  });
  field.addEventListener("blur", () => finish(true));
}
