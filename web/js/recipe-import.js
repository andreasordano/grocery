// Starting a dinner from a recipe someone found: a link to a recipe page, or the recipe's text (an Instagram
// caption, a message; WEB-51). The same box in the dinner editor and on the admin page; each fills its own form
// with what comes back (core/recipe_import.py): name, servings, minutes, what to buy, the method, and the lines
// pantryrun didn't recognise, to add with one tap.
import { esc } from "./format.js";

const $ = selector => document.querySelector(selector);

// What's at home is a name, without the amount: "½ tl soola" → "soola", "40 g maisitärklist" → "maisitärklist".
export const withoutAmount = item =>
  item.replace(/^\s*[\d.,/½¼¾]+\s*(?:(?:kg|g|ml|dl|cl|l|tk|tl|spl)\b\.?)?\s*/i, "").trim() || item;

// One word with a dot and no spaces is a link ("rimi.ee/retseptid/…", "https://…"); anything else is a recipe's text.
export const isLink = v => !/\s/.test(v) && /^(https?:\/\/)?[\w-]+(\.[\w-]+)+([/?#].*)?$/i.test(v);

export function importBox(label, { hidden = false, skipped = [] } = {}) {
  return `<form class="from-link" id="fromLink" autocomplete="off"${hidden ? " hidden" : ""}>
    <label for="dlinkImport">${label}</label>
    <div class="field">
      <textarea id="dlinkImport" rows="1" autocapitalize="off" spellcheck="false" placeholder="Paste a link, or the recipe's text from Instagram or a message"></textarea>
      <button class="btn quiet" type="submit" id="readLink">Read it</button>
    </div>
    <p class="fine" id="linkNote" role="status"></p>
    <div id="skipped">${skippedList(skipped)}</div>
  </form>`;
}

// Lines pantryrun didn't recognise (an English name, a typo): the person adds the ones they buy ([data-unskip]).
export const skippedList = skipped => skipped.length ? `<div class="skipped">
  <p class="fine">pantryrun didn't recognise these. Add the ones you buy:</p>
  <ul>${skipped.map((s, i) => `<li><span lang="et">${esc(s)}</span><button type="button" class="link" data-unskip="${i}">Add</button></li>`).join("")}</ul>
</div>` : "";

function noteFor(found, link) {
  const n = found.items.length, things = `${n} ${n === 1 ? "thing" : "things"} to buy`;
  if (link) {
    const site = new URL(found.link).hostname.replace(/^www\./, "");
    return n ? `Found ${things} on ${site}. Check them, then save. The method stays on ${site}: the dinner links to it.`
      : `${site} doesn't list its ingredients in a way pantryrun can read. Type what you buy for it below.`;
  }
  if (n) return `Added ${things}${found.method ? " and the method" : ""}. Check them, then save.`;
  return found.skipped.length ? "" : "Couldn't find anything to buy in that text. Type what you buy for it below.";
}

async function read(value, userId) {
  const link = isLink(value);
  let res;
  try {
    res = await fetch(link ? "/recipe-import" : "/recipe-text", { method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify(link ? { url: value, user_id: userId } : { text: value, user_id: userId }) });
  } catch {
    throw new Error("Couldn't reach pantryrun. Check your connection, then try again.");
  }
  const found = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(found.detail || (link ? "Couldn't read that page." : "Couldn't read that text."));
  const full = { name: "", servings: null, minutes: null, items: [], staples: [], skipped: [], method: "", ...found };
  return { ...full, note: noteFor(full, link) };
}

// Wire the box drawn by importBox(): fill(found) puts what was read into the page's form (it may redraw the box);
// the note goes under the box afterwards.
export function bindImport(fill, userId = null) {
  const go = async () => {
    const value = $("#dlinkImport").value.trim();
    if (!value) return;
    $("#linkNote").textContent = isLink(value) ? "Reading the page…" : "Reading the text…";
    $("#readLink").disabled = true;
    try {
      const found = await read(value, userId);
      fill(found);
      $("#dlinkImport").value = "";  // read: what it gave is in the form now
      $("#linkNote").textContent = found.note;
    } catch (e) {
      $("#linkNote").textContent = e.message;
    }
    $("#readLink").disabled = false;
  };
  $("#fromLink").onsubmit = e => { e.preventDefault(); e.stopPropagation(); go(); };
  // Enter reads a link straight away; in a recipe's text it starts a new line
  $("#dlinkImport").addEventListener("keydown", e => {
    if (e.key === "Enter" && !e.shiftKey && isLink(e.target.value.trim())) { e.preventDefault(); go(); }
  });
}
