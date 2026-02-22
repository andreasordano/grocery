from search import search_all_stores

products = search_all_stores("Jogurt")

print(len(products))

for p in products:
    print(p)