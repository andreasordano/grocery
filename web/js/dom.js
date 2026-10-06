// The page's fixed elements (see index.html), and a shorthand for finding one.

export const $ = (selector, root = document) => root.querySelector(selector);

export const pick = $("#pick");            // left: the current screen (dinners, the editor or the shopping list)
export const feed = $("#feed");            // right: where the receipt prints
export const after = $("#after");          // under the receipt: what to do with it
export const sheet = $("#sheet");          // the dialog for choosing another product or editing preferences
export const sheetForm = $("#sheetForm");

export const reduceMotion = () => matchMedia("(prefers-reduced-motion: reduce)").matches;
