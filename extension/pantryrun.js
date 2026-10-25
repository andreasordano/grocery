// On pantryrun's page: say the extension is here, and pass a basket the page sends on to the
// background, which opens Rimi (rimi.js fills the cart there). Only well-formed baskets from the
// page itself are accepted.
document.documentElement.dataset.pantryrunCart = "rimi";

const valid = items => Array.isArray(items) && items.length > 0 && items.length <= 60 && items.every(i =>
  i && /^\d{1,12}$/.test(String(i.id)) && typeof i.qty === "number" && i.qty > 0 && i.qty <= 100 &&
  typeof i.name === "string" && i.name.length <= 200);

window.addEventListener("message", e => {
  const d = e.data;
  if (e.source !== window || e.origin !== location.origin || !d || d.source !== "pantryrun" || d.type !== "fill-cart") return;
  if (d.store !== "rimi" || !valid(d.items)) return;
  chrome.runtime.sendMessage({ type: "fill-cart", store: "rimi", items: d.items.map(({ id, qty, name }) => ({ id: String(id), qty, name })) });
});
