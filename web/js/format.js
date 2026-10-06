// Money, amounts and text, written the Estonian way.

export const euro = new Intl.NumberFormat("et-EE", { style: "currency", currency: "EUR" });
export const num = new Intl.NumberFormat("et-EE", { minimumFractionDigits: 2, maximumFractionDigits: 2 });

export const cap = s => s ? s[0].toUpperCase() + s.slice(1) : s;

// Everything shown from data goes through esc() before it's put in the page.
export const esc = s => String(s ?? "").replace(/[&<>"']/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));

// A recipe amount the way a shop writes it: "4 tk", "250 g", "1.5 kg".
export const amount = (n, unit) => n == null || !unit ? "" : unit === "pcs" ? `${+n.toFixed(1)} tk`
  : n >= 1000 ? `${+(n / 1000).toFixed(2)} ${unit === "g" ? "kg" : "l"}` : `${Math.round(n)} ${unit}`;

// "piim, paprika 600g" → ["piim", "paprika 600g"]
export const splitItems = text => text.split(",").map(s => s.trim()).filter(s => s.length >= 2);

// Same spelling-tolerant comparison as the server (core/scoring.py fold).
export const fold = t => t.toLowerCase().replace(/(?<=[gctp])h/g, "").replace(/(.)\1+/g, "$1");
