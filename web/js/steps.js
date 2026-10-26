// The three steps: pick (dinners or a list), see where it's cheapest, say how you'll get it.
// On a computer all three are on the page at once: the steps say where you are, and tapping one scrolls there.
// On a phone each step is a screen of its own (body[data-step], layout.css), and a bar at the bottom shows
// what you have so far and goes to the next step.
import { $ } from "./dom.js";
import { euro, shopName } from "./format.js";
import { state } from "./state.js";
import { picked } from "./dinners.js";
import { ask } from "./basket.js";

const phone = matchMedia("(max-width: 900px)");
const nav = $("#steps"), bar = $("#stepbar");

const filled = () => state.mode === "dinner" ? picked().length : state.items.length;
const answered = () => state.status === "answer" && !!state.result;
const chosen = () => !!state.way && state.way.result_id === state.result?.result_id;
const best = () => state.result?.baskets.find(b => b.store === state.result.store);

// [the long label for computers, the short one for phone tabs]
const labels = () => [
  state.mode === "dinner" ? ["Pick dinners", "Dinners"] : ["Write your list", "List"],
  ["See where it’s cheapest", "Store"],
  ["Get it, in store or online", "Get it"],
];

// Which step can be opened: the answer needs something to price, the last step needs the answer.
const open = n => n === 1 || (n === 2 && filled() > 0) || (n === 3 && answered());

export function goStep(n) {
  if (!open(n)) return;
  state.step = n;
  refreshSteps();
  if (phone.matches) scrollTo({ top: 0 });
  else $([null, "#pick", ".printer", "#after"][n]).scrollIntoView({ behavior: "smooth", block: "start" });
}

// Draw the steps and the bar again: after the basket, the answer or the way to get it changed.
export function refreshSteps() {
  if (state.step > 1 && !filled()) state.step = 1;  // everything was taken out
  if (state.step === 3 && !answered() && state.status !== "pricing") state.step = 2;
  document.body.dataset.step = state.step;

  const done = [filled() > 0, chosen(), chosen()];
  // a computer shows the next thing to do; a phone shows the screen it's on
  const current = phone.matches ? state.step : (done.indexOf(false) + 1 || 3);
  nav.innerHTML = `<ol>${labels().map(([long, short], i) => {
    const n = i + 1, tick = done[i] && n !== current;
    return `<li><button type="button" class="step${tick ? " done" : ""}" data-go="${n}"${n === current ? ` aria-current="step"` : ""}
      ${open(n) ? "" : "disabled"}><span class="n" aria-hidden="true">${tick ? "✓" : n}</span><span class="long">${long}</span><span class="short">${short}</span></button></li>`;
  }).join("")}</ol>`;
  bar.innerHTML = state.step === 1 ? barPick() : state.step === 2 ? barAnswer() : "";
}

// Step 1: what's in the basket, the answer so far, and on to it.
function barPick() {
  const n = filled(), dinner = state.mode === "dinner";
  const what = dinner ? (n ? `${n} ${n === 1 ? "dinner" : "dinners"} in your basket` : "Your basket is empty")
    : (n ? `${n} ${n === 1 ? "thing" : "things"} on your list` : "Your list is empty");
  const b = best();
  const answer = !n ? (dinner ? "Pick a dinner" : "Add what you need")
    : state.status === "pricing" ? "Comparing prices…"
    : state.status === "failed" ? "The stores didn’t answer"
    : answered() && b ? `Cheapest at ${shopName(b.store)} · ${euro.format(b.total_price)}`
    : "Then find the store";
  const find = !dinner && !state.result;
  return `<p class="sb-info"><span>${what}</span><b>${answer}</b></p>
    <button class="btn go" type="button" data-go="2"${find ? " data-find" : ""} ${n ? "" : "disabled"}>${find ? "Find the store" : "See it"}
      <span aria-hidden="true">→</span></button>`;
}

// Step 2: on to how you'll get it.
const barAnswer = () => `<button class="btn go full" type="button" data-go="3" ${answered() ? "" : "disabled"}>How will you get it?
  <span aria-hidden="true">→</span></button>`;

document.addEventListener("click", e => {
  const go = e.target.closest("[data-go]");
  if (!go || go.disabled) return;
  if (go.hasAttribute("data-find")) ask({ fresh: true });  // the shopping list, on a phone: price it on the way
  goStep(+go.dataset.go);
});
phone.addEventListener("change", refreshSteps);
