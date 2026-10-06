// Which screen is on the left: the dinners, writing your own dinner, or the shopping list.
// main.js registers the screens here, so they can switch to one another without importing each other.
// A screen is a module with open() (draw it and set what the receipt shows) and draw() (redraw it only).
import { state } from "./state.js";

const screens = {};

export function addScreen(name, screen) { screens[name] = screen; }

const current = () => state.mode === "list" ? "list" : state.editing ? "editor" : "dinner";

// Open the screen that fits the state.
export function render() {
  state.request++;  // ignore any answer still on its way for the screen before
  screens[current()].open();
}

// Redraw the current screen only, e.g. after something was added to the trip from the receipt.
export function redraw() { screens[current()].draw(); }
