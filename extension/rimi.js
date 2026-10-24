// On Rimi's e-shop: put a basket from pantryrun into the cart, one product at a time, the way
// Rimi's own "add to cart" buttons do (same endpoint, the page's CSRF token, your session).
// A basket is used once and only within 10 minutes of sending it.
const FRESH_MS = 10 * 60 * 1000;

function overlay() {
  const box = document.createElement("div");
  box.setAttribute("role", "status");
  box.style.cssText = "position:fixed;right:20px;bottom:20px;z-index:2147483647;width:320px;padding:18px 20px;" +
    "border-radius:20px;background:#fff;color:#1c1f4a;font:15px/1.4 system-ui,sans-serif;" +
    "box-shadow:0 20px 50px -20px rgba(28,31,74,.6),0 0 0 2px #ff4d6d";
  document.body.append(box);
  return box;
}

// The cart checks a CSRF token against the session. Rimi's front page is cached without one, and
// its own requests while it loads can start a new session, so: wait for the page to settle, then take
// the token from a fresh search page (same session), and take it again if Rimi still says 419.
const sleep = ms => new Promise(r => setTimeout(r, ms));

async function csrfToken() {
  const html = await (await fetch("/epood/ee/otsing?query=piim", { credentials: "same-origin", cache: "no-store" })).text();
  return html.match(/<meta name="csrf-token" content="([^"]+)"/)?.[1] || null;
}

async function addOne(token, item) {
  const body = new URLSearchParams({ _method: "put", _token: token, product: item.id, amount: String(item.qty) });
  const res = await fetch("/epood/cart/change", {
    method: "POST", credentials: "same-origin", body,
    headers: { "X-CSRF-TOKEN": token, "X-Requested-With": "XMLHttpRequest", "Accept": "application/json, text/html" },
  });
  return res.status;
}

(async () => {
  const { pending } = await chrome.storage.local.get("pending");
  if (!pending || pending.store !== "rimi") return;
  await chrome.storage.local.remove("pending");  // once, even if this page is reloaded
  if (Date.now() - pending.at > FRESH_MS) return;
  const box = overlay();
  box.textContent = "pantryrun: getting your Rimi cart ready…";
  await sleep(2500);
  let token = await csrfToken().catch(() => null);
  if (!token) { box.textContent = "pantryrun couldn't fill the cart: Rimi's page has changed. Add the products by hand."; return; }

  const missed = [];
  for (const [i, item] of pending.items.entries()) {
    box.innerHTML = `<b>pantryrun</b><br>Adding to your Rimi cart: ${i + 1} of ${pending.items.length}`;
    try {
      let status = await addOne(token, item);
      if (status === 419) {  // the session changed under us: a fresh token, once
        token = await csrfToken();
        status = await addOne(token, item);
      }
      if (status < 200 || status >= 300) missed.push(item.name);
    } catch { missed.push(item.name); }
  }
  const added = pending.items.length - missed.length;
  box.innerHTML = `<b>pantryrun</b><br>Added ${added} of ${pending.items.length} products to your Rimi cart.` +
    (missed.length ? `<br><span style="color:#d6284b">Not added: ${missed.map(n => n.replace(/[<>&]/g, "")).join(", ")}</span>` : "") +
    `<br><button type="button" style="margin-top:12px;padding:10px 16px;border:0;border-radius:999px;background:#1c1f4a;color:#fff;font:inherit;font-weight:600;cursor:pointer">Show the cart</button>`;
  // Rimi's cart only shows the new products after a reload; then open it.
  box.querySelector("button").onclick = () => { sessionStorage.setItem("pantryrun-open-cart", "1"); location.reload(); };
})();

if (sessionStorage.getItem("pantryrun-open-cart")) {
  sessionStorage.removeItem("pantryrun-open-cart");
  setTimeout(() => document.querySelector(".js-header-cart")?.click(), 800);
}
