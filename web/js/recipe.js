// Recipes: what goes into a dinner for this many people, and how to cook it when that's known (people write it
// for their own dinners; NutriData and the classics only have ingredients). Shown on a dinner's own page
// (dinner-screen.js) and, once dinners are in the trip, as one card per dinner on the left, under the trip,
// with the weekly plan sign-up. The right side keeps only the receipt.
import { $ } from "./dom.js";
import { esc, amount } from "./format.js";
import { state } from "./state.js";
import { logEvent } from "./api.js";
import { dinnerById } from "./dinners.js";
import { shareDinner } from "./share.js";
import { newsletterBox, bindNewsletterBox } from "./newsletter.js";

const wide = matchMedia("(min-width: 901px)");

// "400 g", "2 packs", or what was typed with it ("2 tk")
function howMuch(i) {
  if (i.asked) return i.asked;
  if (i.amount != null) return amount(i.amount, i.unit);
  return i.packs ? `${i.packs} ${i.packs === 1 ? "pack" : "packs"}` : "";
}

// Lines written as a list ("1. Fry…", "- Add…", or just one step per line) become steps.
function method(text) {
  const lines = text.split(/\n+/).map(l => l.trim()).filter(Boolean);
  if (lines.length < 2) return `<p>${esc(lines[0] || "")}</p>`;
  return `<ol>${lines.map(l => `<li>${esc(l.replace(/^(\d+[.)]|[-*•])\s*/, ""))}</li>`).join("")}</ol>`;
}

function link(url) {
  let host;
  try { host = new URL(url).hostname.replace(/^www\./, ""); } catch { return ""; }
  if (!/^https?:/.test(url)) return "";
  return `<a class="rc-link" href="${esc(url)}" target="_blank" rel="noopener">Full recipe on ${esc(host)} <span aria-hidden="true">↗</span></a>`;
}

export const hasPhoto = d => d.image && /^https?:/.test(d.image);

// What's in it and how to cook it: the inside of a card, and of a dinner's own page.
export function recipeBody(d) {
  const own = d.id.startsWith("my-");
  return `<ul class="rc-ing">${d.ingredients.map(i => `<li><span lang="et">${esc(i.label)}</span><span>${esc(howMuch(i))}</span></li>`).join("")}</ul>
    ${d.pantry.length ? `<p class="rc-pantry">From home: <span lang="et">${esc(d.pantry.join(", "))}</span></p>` : ""}
    ${d.method ? `<div class="rc-method"><h4>How to cook it</h4>${method(d.method)}</div>` : ""}
    ${d.link ? link(d.link) : ""}
    ${own && !d.method && !d.link ? `<button type="button" class="link" data-write="${esc(d.id)}">Write down how you cook it</button>` : ""}
    ${d.id.startsWith("nd-") ? `<p class="fine">Amounts from NutriData, Tervise Arengu Instituut. It has no method.</p>` : ""}`;
}

// What you can do with a dinner: change a copy of it (or edit your own), and send it to someone.
export function recipeActions(d) {
  const own = d.id.startsWith("my-");
  return `<p class="rc-actions">${own
      ? `<button type="button" class="link" data-edit-dinner="${esc(d.id)}">Edit</button>`
      : `<button type="button" class="link" data-copy="${esc(d.id)}" title="Change what goes in, or how you cook it, and keep it under Mine">Make it yours</button>`}
    <button type="button" class="link" data-share="${esc(d.id)}">Send to someone</button>
    <span class="fine share-note" role="status"></span></p>`;
}

function card(d, open) {
  const photo = hasPhoto(d);
  return `<details class="rc${photo ? " has-photo" : ""}"${open ? " open" : ""} data-recipe="${esc(d.id)}">
    <summary>${photo ? `<span class="rc-photo"><img src="${esc(d.image)}" alt="" loading="lazy" referrerpolicy="no-referrer"></span>` : ""}<span class="rc-name" lang="et">${esc(d.name)}</span>
      <span class="rc-sub">Recipe for ${d.servings} · ${d.ingredients.length} ${d.ingredients.length === 1 ? "ingredient" : "ingredients"}</span></summary>
    ${recipeBody(d)}
    ${recipeActions(d)}
  </details>`;
}

// Under the trip, on the left: a card per dinner in the answer (open on wide screens when there's just one),
// then the weekly plan sign-up. Empty until the trip has an answer.
export function tripPanel() {
  const dinners = state.mode === "dinner" && state.tripIds.length ? state.result?.dinners ?? [] : [];
  if (!dinners.length) return "";
  return `<section class="recipes" aria-label="${dinners.length > 1 ? "Recipes" : "Recipe"}">
      ${dinners.map(d => card(d, wide.matches && dinners.length === 1)).join("")}</section>
    ${newsletterBox()}`;
}

// A new answer arrived: fill the trip's cards on the left (the dinner screen draws an empty #tripPanel).
export function refreshTripPanel() {
  const panel = $("#tripPanel");
  if (!panel) return;
  panel.innerHTML = tripPanel();
  bindNewsletterBox();
}

document.addEventListener("toggle", e => {
  if (e.target.matches?.(".rc") && e.target.open) {
    logEvent("recipe_open", { recipe_id: e.target.dataset.recipe, result_id: state.result?.result_id ?? null });
  }
}, true);

document.addEventListener("click", e => {
  const write = e.target.closest("[data-write]");
  if (write) { import("./editor-screen.js").then(m => m.editDinner(write.dataset.write)); return; }
  const copy = e.target.closest("[data-copy]");
  if (copy) { import("./editor-screen.js").then(m => m.copyDinner(copy.dataset.copy)); return; }
  const send = e.target.closest("[data-share]");
  if (send) {
    const id = send.dataset.share;
    const d = state.result?.dinners?.find(x => x.id === id) ?? state.viewing?.card ?? dinnerById(id);
    shareDinner({ id, name: d?.name ?? "" }, send.closest(".rc-actions").querySelector(".share-note"));
  }
});
