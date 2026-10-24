// The recipe card under the receipt: what goes into each dinner for this many people, and how to
// cook it when that's known (people write it for their own dinners; NutriData and the classics
// only have ingredients). Folded on phones, so the store answer stays first.
import { after } from "./dom.js";
import { esc, amount } from "./format.js";
import { state } from "./state.js";
import { logEvent } from "./api.js";

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

function card(d, open) {
  const own = d.id.startsWith("my-");
  return `<details class="rc"${open ? " open" : ""} data-recipe="${esc(d.id)}">
    <summary><span class="rc-name" lang="et">${esc(d.name)}</span>
      <span class="rc-sub">Recipe for ${d.servings} · ${d.ingredients.length} ${d.ingredients.length === 1 ? "ingredient" : "ingredients"}</span></summary>
    <ul class="rc-ing">${d.ingredients.map(i => `<li><span lang="et">${esc(i.label)}</span><span>${esc(howMuch(i))}</span></li>`).join("")}</ul>
    ${d.pantry.length ? `<p class="rc-pantry">From home: <span lang="et">${esc(d.pantry.join(", "))}</span></p>` : ""}
    ${d.method ? `<div class="rc-method"><h4>How to cook it</h4>${method(d.method)}</div>` : ""}
    ${d.link ? link(d.link) : ""}
    ${own && !d.method ? `<button type="button" class="link" data-write="${esc(d.id)}">Write down how you cook it</button>` : ""}
    ${d.id.startsWith("nd-") ? `<p class="fine">Amounts from NutriData, Tervise Arengu Instituut. It has no method.</p>` : ""}
  </details>`;
}

// The cards for an answer's dinners: open on wide screens when there's just one.
export function recipeCards(res) {
  const dinners = res.dinners || [];
  if (!dinners.length) return "";
  return `<section class="recipes" aria-label="${dinners.length > 1 ? "Recipes" : "Recipe"}">
    ${dinners.map(d => card(d, wide.matches && dinners.length === 1)).join("")}</section>`;
}

after.addEventListener("toggle", e => {
  if (e.target.matches?.(".rc") && e.target.open) {
    logEvent("recipe_open", { recipe_id: e.target.dataset.recipe, result_id: state.result?.result_id ?? null });
  }
}, true);

after.addEventListener("click", e => {
  const write = e.target.closest("[data-write]");
  if (write) import("./editor-screen.js").then(m => m.editDinner(write.dataset.write));
});
