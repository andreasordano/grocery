// Money, amounts and text, written the Estonian way.

export const euro = new Intl.NumberFormat("et-EE", { style: "currency", currency: "EUR" });
export const num = new Intl.NumberFormat("et-EE", { minimumFractionDigits: 2, maximumFractionDigits: 2 });

export const cap = s => s ? s[0].toUpperCase() + s.slice(1) : s;

// The stores, as the server lists them (stores_config.py, sent with /recipes): set once at start-up.
let known = { stores: {}, chains: {} };
export const setStores = ({ stores, chains }) => { known = { stores: stores ?? {}, chains: chains ?? {} }; };

// The store you walk into: the chain its prices stand for. Barbora is Maxima's e-shop, so "Go to Maxima".
export const shopName = store => known.stores[store]?.shown_as ?? cap(store);
// The e-shop itself, for links, the cart and products: "Barbora".
export const eshopName = store => known.stores[store]?.name ?? cap(store);
// The chain's loyalty card, for its card prices: "Partnerkaart".
export const cardName = store => known.stores[store]?.card ?? "a loyalty card";
// The chains people shop at ({maxima: "Maxima", …}): "Where do you usually shop?"
export const chains = () => known.chains;
// Every store pantryrun prices: ["selver", "rimi", "barbora"]
export const allStores = () => Object.keys(known.stores);

// ["rimi", "barbora"] → "Rimi and Barbora"
export const storeNames = stores => {
  const names = stores.map(eshopName);
  return names.length < 2 ? names.join("") : `${names.slice(0, -1).join(", ")} and ${names.at(-1)}`;
};

// Everything shown from data goes through esc() before it's put in the page.
export const esc = s => String(s ?? "").replace(/[&<>"']/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));

// A recipe amount the way a shop writes it: "4 tk", "250 g", "1.5 kg".
export const amount = (n, unit) => n == null || !unit ? "" : unit === "pcs" ? `${+n.toFixed(1)} tk`
  : n >= 1000 ? `${+(n / 1000).toFixed(2)} ${unit === "g" ? "kg" : "l"}` : `${Math.round(n)} ${unit}`;

// Commas separate items, except between two digits: that's a decimal ("kartul 1,2 kg").
export const ITEM_SEP = /(?<!\d),|,(?!\d)/;

// "piim, kartul 1,2 kg" → ["piim", "kartul 1,2 kg"]
export const splitItems = text => text.split(ITEM_SEP).map(s => s.trim()).filter(s => s.length >= 2);

// Same spelling-tolerant comparison as the server (core/scoring.py fold).
export const fold = t => t.toLowerCase().replace(/(?<=[gctp])h/g, "").replace(/(.)\1+/g, "$1");
