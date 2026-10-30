// The owner's page for pantryrun's own dinners (/admin.html, WEB-53): every dinner with how testers use it,
// edit one, check it at the stores, publish it. Everything goes through /admin/recipes with the owner token
// (EDITION_TOKEN), which this tab keeps until it's closed. Dinners are archived, never deleted: their ids stay.
import { esc } from "./format.js";
import { importBox, bindImport, skippedList } from "./recipe-import.js";

const $ = selector => document.querySelector(selector);
const KEY = "pantryrun.ownerToken";
const MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];
const STATUS = { draft: "Draft", published: "Published", archived: "Archived" };
const FILTERS = [["all", "All"], ["draft", "Drafts"], ["published", "Published"], ["archived", "Archived"]];
const BLANK = { name: "", emoji: "", about: "", servings: 4, minutes: null, tags: [], months: [], ingredients: [], pantry: [],
  method: "", image: "", brand: "", label: "", rights: "", review_by: null, notes: "", status: "draft" };

const st = { token: remembered(), data: null, filter: "all", open: null, dirty: false, skipped: [] };

function remembered() {
  try { return sessionStorage.getItem(KEY) || ""; } catch { return ""; }
}
function remember(token) {
  try { token ? sessionStorage.setItem(KEY, token) : sessionStorage.removeItem(KEY); } catch {}
}

class SignedOut extends Error {}

async function call(method, path, body) {
  const headers = { Authorization: `Bearer ${st.token}`, ...(body ? { "Content-Type": "application/json" } : {}) };
  const res = await fetch(path, { method, headers, body: body ? JSON.stringify(body) : undefined });
  const data = await res.json().catch(() => ({}));
  if (res.status === 401) { signOut("That token isn't the owner's."); throw new SignedOut(); }
  if (!res.ok) throw new Error(typeof data.detail === "string" ? data.detail : `The server answered ${res.status}.`);
  return data;
}

function signOut(note = "") {
  st.token = ""; st.data = null; st.dirty = false;
  remember("");
  $("#admin").hidden = $("#signOut").hidden = true;
  $("#signIn").hidden = false;
  $("#signInNote").textContent = note;
}

async function load(openId = st.open) {
  st.data = await call("GET", "/admin/recipes");
  st.open = openId === "new" || st.data.recipes.some(r => r.id === openId) ? openId : null;
  $("#signIn").hidden = true;
  $("#admin").hidden = $("#signOut").hidden = false;
  drawList();
  drawEditor();
}

// ── the list ─────────────────────────────────────────────────────────────────

const quick = r => r.minutes && r.minutes <= st.data.quick_minutes;
const inSeason = r => r.months.includes(new Date().getMonth() + 1);

function chipNames(r) {
  const names = st.data.chips.filter(c => r.tags.includes(c.id)).map(c => c.name);
  return [...(quick(r) ? ["Quick"] : []), ...(inSeason(r) ? ["In season"] : []), ...names];
}

function drawList() {
  const count = id => st.data.recipes.filter(r => id === "all" || r.status === id).length;
  $("#filters").innerHTML = FILTERS.map(([id, name]) =>
    `<button type="button" data-filter="${id}" aria-pressed="${st.filter === id}">${name} <span class="ad-count">${count(id)}</span></button>`).join("");
  const rows = st.data.recipes.filter(r => st.filter === "all" || r.status === st.filter);
  $("#list").innerHTML = rows.length ? rows.map(r => `<li>
      <button type="button" class="ad-row${r.id === st.open ? " open" : ""}" data-open="${esc(r.id)}">
        <span class="ad-emoji" aria-hidden="true">${esc(r.emoji || "🍽️")}</span>
        <span class="ad-row-main">
          <span class="ad-name" lang="et">${esc(r.name)}</span>
          <span class="ad-row-meta">${esc(chipNames(r).join(" · ") || "No chips")}</span>
        </span>
        <span class="ad-row-side">
          <span class="ad-status ${r.status}">${STATUS[r.status]}</span>
          <span class="ad-use">${r.usage.answers} priced · ${r.usage.people} people</span>
        </span>
      </button></li>`).join("") : `<li class="fine ad-empty">No dinners here.</li>`;
}

// ── one dinner ───────────────────────────────────────────────────────────────

const field = (name, label, control, hint = "") => `<label class="ad-field ad-f-${name}"><span>${label}</span>${control}
  ${hint ? `<small class="fine">${hint}</small>` : ""}</label>`;
const input = (name, value, attrs = "") => `<input name="${name}" value="${esc(value ?? "")}" ${attrs}>`;
const area = (name, value, rows, attrs = "") => `<textarea name="${name}" rows="${rows}" ${attrs}>${esc(value ?? "")}</textarea>`;
const lines = list => (list || []).join("\n");

function usageLine(r) {
  const u = r.usage;
  const last = u.last_used ? `, last on ${new Date(u.last_used).toLocaleDateString("en-GB")}` : "";
  return `<p class="ad-usage">Testers: opened ${u.views}×, priced in ${u.answers} answers for ${u.people} people,
    made theirs ${u.copies}×, cooked ${u.cooked}×${last}.</p>`;
}

function drawEditor() {
  const box = $("#editor");
  if (!st.open) {
    box.innerHTML = `<p class="ad-hint">Pick a dinner, or add a new one. Drafts stay here; only published dinners reach
      the app (within a minute). Archive a dinner instead of deleting it: its id and usage stay.</p>`;
    return;
  }
  const r = st.open === "new" ? BLANK : st.data.recipes.find(x => x.id === st.open);
  const tags = new Set(r.tags);
  st.skipped = [];
  box.innerHTML = `<div class="ad-form-head">
      <h2 lang="et">${esc(r.name || "New dinner")}</h2>
      ${r.id ? `<code class="ad-id">${esc(r.id)}</code>` : `<span class="fine">The id comes from the name and never changes.</span>`}
    </div>
    ${r.id ? usageLine(r) : ""}
    ${importBox(r.id ? "Fill it in from a recipe" : "Start from a recipe", { skipped: st.skipped })}
  <form id="recipe" class="ad-form" novalidate>
    <div class="ad-grid">
      ${field("name", "Name (Estonian)", input("name", r.name, 'required maxlength="80" lang="et"'))}
      ${field("servings", "People", input("servings", r.servings, 'type="number" min="1" max="12" required'))}
      ${field("minutes", "Minutes", input("minutes", r.minutes, 'type="number" min="1" max="600"'),
        `${st.data.quick_minutes} or less is Quick`)}
      ${field("emoji", "Emoji", input("emoji", r.emoji, 'maxlength="8"'), "Shown when there's no photo")}
    </div>
    ${field("about", "On the card (English, one line)", input("about", r.about, 'maxlength="300"'))}
    <fieldset class="ad-set"><legend>Chips</legend>
      <div class="chips">${st.data.chips.map(c =>
        `<button type="button" data-tag="${esc(c.id)}" aria-pressed="${tags.has(c.id)}">${esc(c.name)}</button>`).join("")}</div>
      <small class="fine">Quick comes from the minutes, In season from the months below.</small>
    </fieldset>
    <fieldset class="ad-set"><legend>In season</legend>
      <div class="chips ad-months">${MONTHS.map((m, i) =>
        `<button type="button" data-month="${i + 1}" aria-pressed="${r.months.includes(i + 1)}">${m}</button>`).join("")}</div>
      <small class="fine">None: never under In season.</small>
    </fieldset>
    <div class="ad-grid two">
      ${field("ingredients", "What you buy for it, one per line", area("ingredients", lines(r.ingredients), 9, 'lang="et"'),
        "For that many people, as stores name things: <code>400 g kanafilee</code>, <code>2 tk sibul</code>, <code>till</code>")}
      ${field("pantry", "From home, one per line", area("pantry", lines(r.pantry), 9, 'lang="et"'), "Not priced: <code>sool</code>, <code>õli</code>")}
    </div>
    ${field("method", "How you cook it (English)", area("method", r.method, 8), "Numbered steps, one per line")}
    ${field("image", "Photo address", input("image", r.image, 'type="url" placeholder="https://…"'), "Only photos you may use (see Rights)")}
    <fieldset class="ad-set"><legend>Partner collection</legend>
      <div class="ad-grid">
        ${field("brand", "Brand", input("brand", r.brand))}
        ${field("label", "Label on the card", input("label", r.label, 'placeholder="With Santa Maria"'), "Partner dinners are always labelled")}
      </div>
      ${field("rights", "Rights", input("rights", r.rights, 'placeholder="Recipe and photo by …, agreed on …"'))}
    </fieldset>
    <div class="ad-grid">
      ${field("review_by", "Check again by", input("review_by", r.review_by, 'type="date"'))}
      ${field("status", "Status", `<select name="status">${Object.entries(STATUS).map(([id, name]) =>
        `<option value="${id}"${r.status === id ? " selected" : ""}>${name}</option>`).join("")}</select>`)}
    </div>
    ${field("notes", "Notes (only here)", area("notes", r.notes, 3))}
    <div class="ad-actions">
      <button class="btn dark" type="submit">Save</button>
      <button type="button" class="btn quiet" id="check"${r.id ? "" : " disabled"}>Check at the stores</button>
      <span class="ad-note" id="saveNote" role="status"></span>
    </div>
    <div id="checked" aria-live="polite"></div>
  </form>`;
  bindImport(fill);
}

// What a recipe link or a pasted text gave (js/recipe-import.js), into the form: what's there stays, lines are
// added, and the name and method are filled only when empty. Staples (salt, oil, spices) go under From home, without
// their amounts. The photo isn't taken: only photos we may use (Rights).
const ownLines = el => el.value.split("\n").map(s => s.trim()).filter(Boolean);
const addLines = (el, list) => { el.value = [...new Set([...ownLines(el), ...list])].join("\n"); };

function fill(found) {
  const f = $("#recipe").elements;
  if (!f.name.value.trim() && found.name) f.name.value = found.name;
  if (found.servings) f.servings.value = found.servings;
  if (found.minutes) f.minutes.value = found.minutes;
  addLines(f.ingredients, found.items.filter(i => !found.staples.includes(i)));
  addLines(f.pantry, found.staples.map(s => s.replace(/^\s*[\d.,/½¼¾]+\s*(?:(?:kg|g|ml|dl|cl|l|tk|tl|spl)\b\.?)?\s*/i, "")));
  if (!f.method.value.trim() && found.method) f.method.value = found.method;
  st.skipped = found.skipped;
  $("#skipped").innerHTML = skippedList(st.skipped);
  st.dirty = true;
}

function unskip(i) {
  const [line] = st.skipped.splice(i, 1);
  addLines($("#recipe").elements.ingredients, [line]);
  $("#skipped").innerHTML = skippedList(st.skipped);
  st.dirty = true;
}

function readForm() {
  const f = $("#recipe"), v = name => f.elements[name].value;
  const pressed = sel => [...f.querySelectorAll(`${sel}[aria-pressed="true"]`)];
  return {
    name: v("name"), emoji: v("emoji"), servings: v("servings"), minutes: v("minutes"), about: v("about"),
    tags: pressed("[data-tag]").map(b => b.dataset.tag), months: pressed("[data-month]").map(b => Number(b.dataset.month)),
    ingredients: v("ingredients"), pantry: v("pantry"), method: v("method"), image: v("image"),
    brand: v("brand"), label: v("label"), rights: v("rights"), review_by: v("review_by"), status: v("status"), notes: v("notes"),
  };
}

const note = text => { const n = $("#saveNote"); if (n) n.textContent = text; };

async function save() {
  note("Saving…");
  try {
    const body = readForm();
    const saved = st.open === "new" ? await call("POST", "/admin/recipes", body)
      : await call("PUT", `/admin/recipes/${encodeURIComponent(st.open)}`, body);
    st.dirty = false;
    await load(saved.id);
    note(saved.status === "published" ? "Saved. The app shows it within a minute." : "Saved.");
  } catch (e) {
    if (!(e instanceof SignedOut)) note(e.message);
  }
}

async function check() {
  const out = $("#checked");
  out.innerHTML = `<p class="fine">Asking every store, as a tester would… ${st.dirty ? "(saved changes only)" : ""}</p>`;
  try {
    const { stores } = await call("POST", `/admin/recipes/${encodeURIComponent(st.open)}/check`);
    out.innerHTML = `<table class="ad-check"><thead><tr><th>Store</th><th>Total</th><th>Missing</th></tr></thead><tbody>
      ${stores.map(s => `<tr><td>${esc(s.store)}</td>
        <td>${s.status === "ok" ? `${s.total.toFixed(2)} €` : "didn't answer"}</td>
        <td lang="et">${s.status !== "ok" ? "" : s.missing.length ? esc(s.missing.join(", ")) : "nothing: it can sell all of it"}</td></tr>`).join("")}
    </tbody></table>`;
  } catch (e) {
    if (!(e instanceof SignedOut)) out.innerHTML = `<p class="ad-note">${esc(e.message)}</p>`;
  }
}

function leave() {
  return !st.dirty || confirm("Leave this dinner without saving the changes?");
}

// ── wiring ───────────────────────────────────────────────────────────────────

document.addEventListener("click", e => {
  const toggle = e.target.closest("[data-tag], [data-month]");
  if (toggle) {
    toggle.setAttribute("aria-pressed", String(toggle.getAttribute("aria-pressed") !== "true"));
    st.dirty = true;
    return;
  }
  const filter = e.target.closest("[data-filter]");
  if (filter) { st.filter = filter.dataset.filter; drawList(); return; }
  const open = e.target.closest("[data-open]");
  if (open && open.dataset.open !== st.open && leave()) {
    st.open = open.dataset.open; st.dirty = false;
    drawList(); drawEditor();
    return;
  }
  if (e.target.closest("#new") && leave()) {
    st.open = "new"; st.dirty = false;
    drawList(); drawEditor();
    $("#recipe").elements.name.focus();
    return;
  }
  if (e.target.closest("#check")) { check(); return; }
  const skipped = e.target.closest("[data-unskip]");
  if (skipped) { unskip(+skipped.dataset.unskip); return; }
  if (e.target.closest("#signOut") && leave()) signOut();
});

document.addEventListener("input", e => { if (e.target.closest("#recipe")) st.dirty = true; });
document.addEventListener("submit", e => {
  e.preventDefault();
  if (e.target.id === "recipe") { save(); return; }
  if (e.target.id === "signIn") {
    st.token = $("#token").value.trim();
    remember(st.token);
    load(null).catch(err => { if (!(err instanceof SignedOut)) $("#signInNote").textContent = err.message; });
  }
});
window.addEventListener("beforeunload", e => { if (st.dirty) e.preventDefault(); });

if (st.token) load(null).catch(err => { if (!(err instanceof SignedOut)) signOut(err.message); });
else signOut();
