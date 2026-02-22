# =============================================================================
# This module contains the core optimization logic for selecting the best combination of products based on their scores and prices. 
# The main function, `optimize_cart`, takes a list of all products from the database, a grocery list, and selected stores, 
# and returns the best cart along with its total score and price.
# It runs after the scoring phase, which assigns a score to each product based on various factors (see scoring.py) and before the final output formatting.
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