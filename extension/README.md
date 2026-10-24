# pantryrun: fill my Rimi cart (browser extension, in testing)

Puts the basket pantryrun recommends at Rimi into your Rimi e-shop cart. It runs only in your
browser: it uses Rimi's own "add to cart" request with your Rimi session, so your login never
reaches pantryrun. It doesn't check out or pay; you review the cart on rimi.ee.

How it works: on pantryrun's receipt for Rimi, "Send to Rimi cart" passes the products (Rimi
product code and amount) to the extension, which opens rimi.ee and adds them one by one.

## Install (Chrome or Edge on a computer)

It isn't in the Chrome Web Store. To try it:

1. Open `chrome://extensions` and turn on **Developer mode** (top right).
2. Click **Load unpacked** and choose this `extension/` folder.
3. Open pantryrun, pick a dinner, switch the receipt to Rimi, then **Send to Rimi cart**.

## Limits

- Rimi only, and only on computers (no extensions on phones).
- If Rimi changes its site, adding stops working; the box on rimi.ee then says so.
- Rimi's cart sets the amount for a product: a product already in your cart gets pantryrun's amount.
- Loose goods go in by weight (kg), as priced on the receipt.
