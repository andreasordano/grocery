// Suggestions while typing: product words from the store catalogs
// (web/vocab.json, built by scripts/build_vocab.py as [word, products, shelf], most used first).
import { fold } from "./format.js";

let vocab = null, loading = null;

// Loaded the first time someone focuses an item field; what's already typed is looked up once it arrives.
export function loadVocab() {
  loading ||= fetch("/vocab.json").then(r => r.json())
    .then(words => { vocab = words.map(([w, n, s]) => ({ w, s, f: fold(w) })); })
    .then(() => { const el = document.activeElement; if (el?.id === "item" && el.value) el.dispatchEvent(new Event("input")); })
    .catch(() => { loading = null; });
}

// Edit distance, giving up past `max` (typos like "maapäklivõi").
function within(a, b, max) {
  if (Math.abs(a.length - b.length) > max) return false;
  let prev = Array.from({ length: b.length + 1 }, (_, j) => j);
  for (let i = 1; i <= a.length; i++) {
    const row = [i];
    for (let j = 1; j <= b.length; j++) row[j] = Math.min(prev[j] + 1, row[j - 1] + 1, prev[j - 1] + (a[i - 1] === b[j - 1] ? 0 : 1));
    if (Math.min(...row) > max) return false;
    prev = row;
  }
  return prev[b.length] <= max;
}

// Words that start with what was typed, then words containing it, then close typos.
export function suggest(text) {
  const q = fold(text.trim());
  if (!vocab || q.length < 2) return [];
  const starts = [], inside = [], typos = [];
  for (const v of vocab) {
    if (v.f.startsWith(q)) starts.push(v);
    else if (q.length >= 3 && v.f.includes(q)) inside.push(v);
    else if (q.length >= 5 && within(v.f, q, 2)) typos.push(v);
  }
  return [...starts, ...inside, ...typos].slice(0, 6);
}

// An amount typed before or after the name ("600g paprika", "paprika 600 g", "2 piim"); same units as the server.
const QTY = String.raw`\d+(?:[.,]\d+)?\s*(?:kg|g|dl|cl|ml|l|tk|x|×)?`;
export function splitQty(text) {
  let m = text.match(new RegExp(String.raw`^(${QTY}\s+)(\S.*)$`, "i"));
  if (m) return { lead: m[1], name: m[2], trail: "" };
  m = text.match(new RegExp(String.raw`^(.*\S)(\s+${QTY})$`, "i"));
  if (m) return { lead: "", name: m[1], trail: m[2] };
  return { lead: "", name: text, trail: "" };
}
