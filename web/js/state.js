// Everything the page keeps track of while it's open. Screens change it, then redraw.
import { storage } from "./storage.js";

export const state = {
  mode: "dinner",      // "dinner" or "list": the switch in the top bar
  recipes: [],         // hand-written classics
  dishes: [],          // NutriData dishes: {id, name, category}
  categories: [],      // {id, name}
  category: storage.get("pantryrun.category", "ideas"),
  shown: [],           // dinner ids on screen; kept until the category changes or "Show me others"
  mine: [],            // this person's own dinners: {id, name, servings, items}
  editing: null,       // the dinner being written: {id or null, name, servings, items}
  shared: null,        // a dinner someone sent by link: {id "sh-…", token, name, servings, items, saved}
  recipeId: null,      // the picked dinner
  servings: 2,
  extras: [],          // dinner: anything else for this trip
  extrasOpen: false,   // the field for those is folded away until asked for
  items: [],           // shopping list
  prefs: storage.get("pantryrun.prefs", {}),  // {key: {words: [], products: {store: name}}}
  result: null,        // last /basket answer for the current mode
  view: null,          // store whose receipt is showing
  request: 0,          // counts requests, so an answer that arrives late is ignored
};
