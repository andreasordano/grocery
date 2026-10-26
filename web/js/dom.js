// The page's fixed elements (see index.html), and a shorthand for finding one.

export const $ = (selector, root = document) => root.querySelector(selector);

export const pick = $("#pick");            // 1, left: the current screen (dinners, the editor or the shopping list)
export const feed = $("#feed");            // 2, right: where the receipt prints
export const under = $("#under");          // under the receipt: e-shop prices, a wrong product
export const after = $("#after");          // 3, below the receipt: how you'll get it
export const heroText = $("#heroText");    // the current screen's headline, across the top
export const sheet = $("#sheet");          // the dialog for choosing another product or editing preferences
export const sheetForm = $("#sheetForm");

export const reduceMotion = () => matchMedia("(prefers-reduced-motion: reduce)").matches;
