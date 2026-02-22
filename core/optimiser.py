# =============================================================================
# OPTIMIZER
# =============================================================================

def optimize_cart(all_products, grocery_list, selected_stores):

    best_cart = []
    total_score = 0.0

    for name in grocery_list:

        products = all_products.get(name, [])

        valid = [
            p for p in products
            if p["store"] in selected_stores
        ]

        if not valid:
            continue

        best = min(valid, key=lambda p: p.get("score", float("inf")))

        best_cart.append(best)
        total_score += best.get("score", 0.0)

    total_price = sum(p["price"] for p in best_cart)

    info = {
        "total_score": round(total_score, 2),
        "total_price": round(total_price, 2),
        "stores": list(set(p["store"] for p in best_cart))
    }

    return best_cart, info["total_score"], info