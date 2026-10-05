# =============================================================================
# This module turns scored candidates into a single-store recommendation.
# The product answer is "go to one store, buy this", so baskets are never split
# across stores. For each store we pick the best-scored product per item, then
# rank stores by coverage (fewest missing items) and then by total price.
# It runs after the fetch/scoring phase (see fetch.py and scoring.py).
# =============================================================================

def store_basket(all_products, items, store):
    """Best-scored product per item at one store, plus the items it lacks."""
    cart = []
    missing = []
    for name in items:
        candidates = [p for p in all_products.get(name, []) if p["store"] == store]
        if not candidates:
            missing.append(name)
            continue
        cart.append(min(candidates, key=lambda p: p.get("score", float("inf"))))

    return {
        "store": store,
        "cart": cart,
        "missing": missing,
        "total_price": round(sum(p["price"] for p in cart), 2),
        "total_score": round(sum(p.get("score", 0.0) for p in cart), 2),
    }


def optimize_cart(all_products, items, selected_stores):
    """Return (cart, total_score, info) for the recommended single store.

    info["baskets"] holds every store's summary, best first, so the caller can
    show alternatives. Returns an empty cart when no store has any item.
    """
    baskets = [store_basket(all_products, items, s) for s in selected_stores]
    baskets.sort(key=lambda b: (len(b["missing"]), b["total_price"]))
    baskets = [b for b in baskets if b["cart"]]

    if not baskets:
        return [], 0.0, {"store": None, "total_price": 0.0, "missing": list(items), "baskets": []}

    best = baskets[0]
    info = {
        "store": best["store"],
        "total_price": best["total_price"],
        "missing": best["missing"],
        "baskets": [
            {k: b[k] for k in ("store", "total_price", "missing")}
            for b in baskets
        ],
    }
    return best["cart"], best["total_score"], info
