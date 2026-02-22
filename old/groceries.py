# ! File-level: Grocery Cart Optimizer (e-store focused)
# ! This script scrapes online grocery stores, scores products, and
# ! suggests an optimized shopping cart balancing price and relevance.

import streamlit as st
import itertools
import re
from collections import defaultdict
from urllib.parse import quote
import pandas as pd
import json

from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

# =========================
# CONFIGURATION
# =========================

STORES_CONFIG = {
    "selver": {
        "url": "https://www.selver.ee/search?q={}",
        "wait": (By.CLASS_NAME, "ProductCard"),
        "items": (By.CLASS_NAME, "ProductCard"),
        "name": lambda e: e.find_element(By.CLASS_NAME, "ProductCard__title").text,
        "price": lambda e: e.find_element(By.CLASS_NAME, "ProductPrice").text.split("\n")[0],
    },
    "barbora": {
        "url": "https://barbora.ee/otsing?q={}",
        "wait": (By.CSS_SELECTOR, 'li[data-testid^="product-card-"]'),
        "items": (By.CSS_SELECTOR, 'li[data-testid^="product-card-"]'),
        "name": lambda e: e.get_attribute("data-cnstrc-item-name"),
        "price": lambda e: f"{e.get_attribute('data-cnstrc-item-price')} €",
    },
    "rimi": {
        "url": "https://www.rimi.ee/epood/en/search?query={}",
        "wait": (By.CLASS_NAME, "product-grid__item"),
        "items": (By.CLASS_NAME, "product-grid__item"),
        "name": lambda e: e.find_element(By.CLASS_NAME, "card__name").text,
        "price": lambda e: json.loads(e.find_element(By.CLASS_NAME, "js-product-container").get_attribute("data-gtm-eec-product"))["price"]
}
}

# =========================
# RULES / UTILITIES
# =========================

ITEM_RULES = {
    "leib": {
        "include": ["leib"],
        "exclude": ["sai", "kukkel", "ciabatta", "mini", "väike"],
        "min_weight_g": 300
    },
    "piim": {
        "include": ["piim"],
        "exclude": ["šok", "batoon", "müsli", "jogurt", "dessert"],
        "min_volume_ml": 500
    },
    "kohuke": {
        "include": ["kohuke", "alma", "tere", "karums"],
        "exclude": ["magija"],
        "min_weight_g": 20
    },
    "broiler": {
        "include": ["kana", "rinnafilee", "kanaliha", "kintsuliha", "broiler"],
        "exclude": ["maksa", "südame", "kael", "pihvid", "nugget", "kartul", "kast", "seen", "magus", "juust", "suitsu", "kass", "koer"],
        "min_weight_g": 300
    }
}

def parse_price(price_str):
    # handle numeric inputs returned by site JSON
    if price_str is None:
        return float("inf")
    if isinstance(price_str, (int, float)):
        try:
            return float(price_str)
        except Exception:
            return float("inf")

    s = str(price_str)
    s = s.replace("€", "").replace(",", ".").strip()
    try:
        return float(s)
    except Exception:
        return float("inf")


def extract_weight_volume(name):
    name = name.lower()

    matches = re.findall(r"(\d+(?:[.,]\d+)?)\s*(kg|g|ml|l)\b", name)

    weight = None
    volume = None

    for value, unit in matches:
        value = float(value.replace(",", "."))

        if unit == "kg":
            weight = value * 1000
        elif unit == "g":
            weight = value
        elif unit == "l":
            volume = value * 1000
        elif unit == "ml":
            volume = value

    return weight, volume


def relevance_score(item, name):
    rules = ITEM_RULES[item]
    name_l = name.lower()
    score = 0

    # use word-boundary regex to avoid substring false-positives
    for w in rules["include"]:
        if w in name_l:
            score += 3
    for w in rules["exclude"]:
        if w in name_l:
            score -= 5

    weight, volume = extract_weight_volume(name)

    if "min_weight_g" in rules and weight:
        score += 3 if weight >= rules["min_weight_g"] else -10
    if "min_volume_ml" in rules and volume:
        score += 3 if volume >= rules["min_volume_ml"] else -10

    return score

# =========================
# SCRAPER
# =========================

@st.cache_resource
def get_driver():
    from selenium.webdriver.chrome.options import Options
    options = Options()

    options.add_argument("--start-maximized")
    options.add_argument("--disable-blink-features=AutomationControlled")
    options.add_argument("--user-agent=Mozilla/5.0")

    driver = webdriver.Chrome(options=options)
    driver.set_page_load_timeout(60)

    return driver



def scrape_store(driver, store, item):
    cfg = STORES_CONFIG[store]
    driver.get(cfg["url"].format(quote(item)))

    products = []
    try:
        WebDriverWait(driver, 30).until(
            EC.presence_of_all_elements_located(cfg["wait"])
        )
        elems = driver.find_elements(*cfg["items"])
        print(f"{store}: found {len(elems)} elements for {item}")


        for e in elems:
            try:
                name = cfg["name"](e)
                price = parse_price(cfg["price"](e))

                score = relevance_score(item, name)
                print(f"DEBUG: {name} | score={score} | price={price}")


                if score <= 2:
                    continue

                products.append({
                    "item": item,
                    "store": store,
                    "name": name.strip(),
                    "price": price,
                    "relevance": score
                })
            except Exception:
                pass
    except Exception:
        pass

    return products


def scrape_all_products(items, selected_stores):
    driver = get_driver()
    all_products = defaultdict(list)
    
    total_searches = len(items) * len(selected_stores)
    progress_bar = st.progress(0)
    status_text = st.empty()
    
    count = 0
    for item in items:
        for store in selected_stores:
            status_text.text(f"Searching {store} for {item}...")
            products = scrape_store(driver, store, item)
            all_products[item].extend(products)
            count += 1
            progress_bar.progress(count / total_searches)
    
    progress_bar.empty()
    status_text.empty()
    
    return all_products

# =========================
# OPTIMIZER (price + relevance only)
# =========================

def optimize_cart(all_products, items, selected_stores):
    product_lists = []
    
    for item in items:
        valid_products = [p for p in all_products[item] if p["store"] in selected_stores]
        if not valid_products:
            return None, None, None
        product_lists.append(valid_products)

    best_score = float("inf")
    best_cart = None
    best_info = None

    for combo in itertools.product(*product_lists):
        total_price = sum(p["price"] for p in combo)
        relevance_penalty = sum(max(0, 5 - p["relevance"]) for p in combo)
        score = total_price + relevance_penalty

        if score < best_score:
            best_score = score
            best_cart = combo
            best_info = {"stores": set(p["store"] for p in combo)}

    return best_cart, best_score, best_info

# =========================
# STREAMLIT UI 
# =========================

st.set_page_config(page_title="Grocery Optimizer", layout="centered")
st.title("🛒 Grocery Cart Optimizer — E-stores only")
st.write("Optimizes grocery price + relevance across e-stores (no geolocation)")

st.subheader("Your grocery list")
store_options = list(STORES_CONFIG.keys())
selected_stores = st.multiselect("Stores to include", options=store_options, default=store_options)
items = st.multiselect("Items to buy", options=list(ITEM_RULES.keys()), default=["leib", "piim"])

if "analysis_result" not in st.session_state:
    st.session_state["analysis_result"] = None

if st.button("🔍 Find best cart", type="primary"):
    if not items:
        st.error("Please select at least one item")
    elif not selected_stores:
        st.error("Please select at least one store")
    else:
        with st.spinner("Scraping products from e-stores..."):
            all_products = scrape_all_products(items, selected_stores)
        
        filtered_products = defaultdict(list)
        for item, plist in all_products.items():
            filtered_products[item] = [p for p in plist if p["store"] in selected_stores]

        missing = [item for item in items if not filtered_products[item]]
        if missing:
            #print message about missing items in selected stores and all the variables for each function for debugging
            st.write(f"Debug info: all_products={all_products}, filtered_products={filtered_products}, missing={missing}")
            st.session_state["analysis_result"] = {"error": f"No products found in selected stores for: {', '.join(missing)}"}
        else:
            with st.spinner("Optimizing cart..."):
                cart, score, info = optimize_cart(filtered_products, items, selected_stores)
            if cart is None:
                st.session_state["analysis_result"] = {"error": "Could not find a valid combination"}
            else:
                st.session_state["analysis_result"] = {
                    "cart": cart,
                    "score": score,
                    "info": info,
                    "filtered_products": filtered_products,
                    "items": items,
                    "selected_stores": selected_stores
                }

# Display results
if st.session_state["analysis_result"]:
    res = st.session_state["analysis_result"]
    if "error" in res:
        st.error(res["error"])
    else:
        filtered_products = res["filtered_products"]
        cart = res["cart"]
        score = res["score"]
        res_items = res["items"]
        stores = res.get("selected_stores", [])

        if stores:
            st.subheader("📊 Individual Store Comparison")
            comparison_data = []
            for store in stores:
                store_total = 0
                store_missing = 0
                for item in res_items:
                    candidates = [p for p in filtered_products[item] if p["store"] == store]
                    if candidates:
                        best = min(candidates, key=lambda p: p["price"])
                        store_total += best["price"]
                    else:
                        store_missing += 1
                comparison_data.append({
                    "Store": store.capitalize(),
                    "Grocery Cost": store_total,
                    "Missing Items": store_missing
                })

            df = pd.DataFrame(comparison_data)
            if not df.empty:
                display_df = df.copy()
                display_df["Grocery Cost"] = display_df["Grocery Cost"].map('{:.2f} €'.format)
                st.dataframe(display_df, hide_index=True)

                complete_options = df[df["Missing Items"] == 0]
                if not complete_options.empty:
                    best_store = complete_options.loc[complete_options["Grocery Cost"].idxmin()]
                    st.info(f"💡 Best single store: **{best_store['Store']}** (Total: {best_store['Grocery Cost']:.2f} €)")
                elif len(stores) > 1:
                    st.warning("No single store has all items. Combining stores may be necessary.")

        st.markdown("---")
        st.subheader("Top relevant products (in selected stores)")
        for item in res_items:
            st.markdown(f"**{item.capitalize()}**")
            prods = sorted(filtered_products[item], key=lambda p: (-p['relevance'], p['price']))[:5]
            for p in prods:
                st.write(f"{p['name']} ({p['store']}) – {p['price']:.2f} € [relevance={p['relevance']}]")
            st.markdown("---")

        st.subheader("✅ Best cart")
        total = 0
        for p in cart:
            st.write(f"**{p['item']}** → {p['name']} ({p['store']}) – {p['price']:.2f} €")
            total += p["price"]

        st.markdown("---")
        st.write(f"Groceries total: **{total:.2f} €**")
        st.write(f"Final score (Price + Penalty): **{score:.2f}**")
