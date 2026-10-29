// Everything the page keeps track of while it's open. Screens change it, then redraw.
import { storage } from "./storage.js";

export const state = {
  mode: "dinner",      // "dinner" or "list": the switch in the top bar
  recipes: [],         // hand-written classics
  dishes: [],          // pantryrun's own and store recipes: {id, name, tags, minutes, count, photo, category?, label?}
  categories: [],      // the chips: {id, name, moment?}
  category: storage.get("pantryrun.category", "ideas"),
  shown: [],           // dinner ids on screen; kept until the category changes or "Show me others"
  mine: [],            // this person's own dinners: {id, name, servings, items}
  editing: null,       // the dinner being written: {id or null, name, servings, items}
  shared: null,        // a dinner someone sent by link: {id "sh-…", token, name, servings, items, saved}
  plan: null,          // a weekly plan from the newsletter (?plan=): {token, title, dinners: [{id, featured, …}]}
  viewing: null,       // the dinner whose own page is open: {id, card (its recipe, once loaded), failed}
  recipeId: null,      // the dinner picked last
  tripIds: [],         // the dinners in the basket, in the order picked (dinners.js)
  servings: 2,         // the headline's number: for dinners without their own (dinners.js peopleFor)
  people: {},          // dinner id → how many people it's for, once chosen on its page or the headline
  extras: [],          // dinner: anything else for the basket
  skipped: [],         // receipt lines taken off with ×, at every store: {key, label}
  extrasOpen: false,   // the field for those is folded away until asked for
  items: [],           // shopping list
  prefs: storage.get("pantryrun.prefs", {}),  // {key: {words: [], products: {store: name}}}
  result: null,        // last /basket answer for the current mode
  status: "idle",      // the receipt: "idle", "pricing", "failed" or "answer"
  way: null,           // how they'll get it: {result_id, store, via: "store" | "online" | "delivery"}
  step: 1,             // phones: the step on screen (js/steps.js)
  view: null,          // store whose receipt is showing
  request: 0,          // counts requests, so an answer that arrives late is ignored
};
