// The Shopping list screen: type what you need, then find the one store that has it all.
import { pick } from "./dom.js";
import { esc } from "./format.js";
import { state } from "./state.js";
import { bindAdd, itemButton, itemClick } from "./items.js";
import { ask } from "./basket.js";
import { idle } from "./receipt.js";

const addWhatYouNeed = () => idle("Add what you need", "We'll find the one store that has it all.");

export function open() {
  draw();
  addWhatYouNeed();
}

export function draw() {
  pick.innerHTML = `
    <h1>What do you need?</h1>
    <p class="sub">Type a few things, separated by commas. Add an amount if you like.</p>
    <form class="field" id="add" autocomplete="off">
      <input id="item" placeholder="piim, paprika 600g, 2 leib" aria-label="Add items" enterkeyhint="done">
      <button class="btn quiet" type="submit">Add</button>
    </form>
    <ul class="items">${state.items.length ? state.items.map((it, i) => `
      <li>${itemButton(it, i)}<button type="button" data-remove="${i}" aria-label="Remove ${esc(it)}">×</button></li>`).join("")
      : `<li class="none">Nothing on the list yet.</li>`}
    </ul>
    <button class="btn dark" id="find" type="button" ${state.items.length ? "" : "disabled"}>Find the store</button>`;
  bindAdd(state.items, changed);
  pick.onclick = onClick;
}

// After the list changes: redraw, and price it again if there's an answer showing.
function changed() {
  draw();
  if (!state.items.length) addWhatYouNeed();
  else if (state.result) ask();
}

function onClick(e) {
  if (itemClick(e, state.items, changed)) return;
  if (e.target.closest("#find")) ask({ fresh: true });
}
