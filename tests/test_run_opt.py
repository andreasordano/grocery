from core.optimiser import optimize_cart

all_products = {
    "piim": [{"name":"P1","store":"rimi","price":1.0,"score":1.0,"item":"piim"}],
    "leib": [{"name":"L1","store":"rimi","price":2.0,"score":1.0,"item":"leib"}],
    "kana": [{"name":"K1","store":"rimi","price":3.0,"score":1.0,"item":"kana"}],
}

grocery_list = {"piim":{}, "leib":{}, "kana":{}}

cart, score, info = optimize_cart(all_products, grocery_list, ["rimi"])
print("cart:", cart)
print("score:", score)
print("info:", info)
