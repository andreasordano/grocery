// Recipes: what goes into a dinner for this many people, and how to cook it when that's known (people write it
// for their own dinners and the classics have one; a store's recipe links to its method; NutriData has none).
// Shown on a dinner's own page (dinner-screen.js), opened from the dinners or from "Recipe" on a dinner in the basket.
import { esc, amount } from "./format.js";
import { state } from "./state.js";
import { dinnerById } from "./dinners.js";
import { shareDinner } from "./share.js";

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

const host = url => { try { return /^https?:/.test(url) ? new URL(url).hostname.replace(/^www\./, "") : ""; } catch { return ""; } };

function link(url) {
  return host(url) ? `<a class="rc-link" href="${esc(url)}" target="_blank" rel="noopener">Full recipe on ${esc(host(url))} <span aria-hidden="true">↗</span></a>` : "";
}

// A store's recipe: the method stays on its page, so the way there is the "How to cook it".
function methodThere(d) {
  if (!host(d.link)) return "";
  const steps = d.steps ? `${d.steps} steps` : "Step by step";
  return `<div class="rc-method"><h4>How to cook it</h4>
    <a class="rc-there" href="${esc(d.link)}" target="_blank" rel="noopener"><span><b>${steps}${d.minutes ? `, ${d.minutes} min` : ""}</b>
      on ${esc(host(d.link))}</span><span aria-hidden="true">↗</span></a></div>`;
}

export const hasPhoto = d => d.image && /^https?:/.test(d.image);

// What's in it and how to cook it: the inside of a card, and of a dinner's own page.
export function recipeBody(d) {
  const own = d.id.startsWith("my-");
  return `<ul class="rc-ing">${d.ingredients.map(i => `<li><span lang="et">${esc(i.label)}</span><span>${esc(howMuch(i))}</span></li>`).join("")}</ul>
    ${d.pantry.length ? `<p class="rc-pantry">From home: <span lang="et">${esc(d.pantry.join(", "))}</span></p>` : ""}
    ${d.method ? `<div class="rc-method"><h4>How to cook it</h4>${method(d.method)}</div>` : ""}
    ${d.link && !d.method && d.id.startsWith("rm-") ? methodThere(d) : d.link ? link(d.link) : ""}
    ${own && !d.method && !d.link ? `<button type="button" class="link" data-write="${esc(d.id)}">Write down how you cook it</button>` : ""}
    ${d.id.startsWith("nd-") ? `<p class="fine">Amounts from NutriData, Tervise Arengu Instituut. It has no method.</p>` : ""}
    ${d.id.startsWith("rm-") ? `<p class="fine">Recipe and photo from Rimi. pantryrun prices it at every store.</p>` : ""}`;
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
