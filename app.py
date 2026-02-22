# groceries_v2.py — Grocery Cart Optimizer with interactive product selection
#
# Key improvements over v1:
#   - Hierarchical product catalog (category → product) replaces hard-coded ITEM_RULES
#   - User controls quantity, minimum size, and keyword preferences per product
#   - Scoring uses unit price per 100g/100ml (larger packs are not penalised)
#   - Results table shows full score breakdown for full transparency

import streamlit as st
import re
from collections import defaultdict
import pandas as pd
import sys
import os
sys.path.insert(0, os.path.dirname(__file__))
from catalog.catalog import load_catalog
from core.optimiser import optimize_cart
import requests

# Default API URL (change in sidebar if your API runs elsewhere)
DEFAULT_API_URL = os.environ.get("GROCERIES_API_URL", "http://localhost:8000")


# =============================================================================
# PRODUCT CATALOG  (category → product → defaults)
# Everything here is just a starting point; the user overrides via the UI.
# =============================================================================

PRODUCT_CATALOG = load_catalog()

# =============================================================================
# STORE CONFIGURATION
# =============================================================================

STORES = ["selver", "barbora", "rimi"]


# =============================================================================
# SESSION STATE INIT
# =============================================================================

st.set_page_config(page_title="Grocery Optimizer", layout="wide")
st.title("🛒 Grocery Cart Optimizer")

if "grocery_list" not in st.session_state:
    st.session_state["grocery_list"] = {}

if "analysis_result" not in st.session_state:
    st.session_state["analysis_result"] = None

# =============================================================================
# SIDEBAR — current list + store picker + search button
# =============================================================================

with st.sidebar:
    st.header("🛍️ Your grocery list")

    if not st.session_state["grocery_list"]:
        st.info("No items yet. Browse the catalog on the right and check the products you want.")
    else:
        to_remove = []
        for name, spec in st.session_state["grocery_list"].items():
            col1, col2 = st.columns([5, 1])
            col1.markdown(
                f"**{name}**  \n"
                f"qty: {spec['qty']} · min: {spec['user_min']} {spec.get('unit','g')}"
            )
            if col2.button("✕", key=f"remove_{name}"):
                to_remove.append(name)
        for name in to_remove:
            del st.session_state["grocery_list"][name]
            st.rerun()

    st.markdown("---")
    store_options = STORES
    selected_stores = st.multiselect(
        "Stores to search",
        options=store_options,
        default=store_options,
        key="selected_stores",
    )

    api_url = st.text_input("Optimizer API URL", value=DEFAULT_API_URL, key="api_url")

    st.markdown("---")
    find_disabled = not st.session_state["grocery_list"] or not selected_stores
    if st.button("🔍 Find best cart", type="primary", disabled=find_disabled):
        # Build items list from user's selections (use display names)
        items = list(st.session_state["grocery_list"].keys())

        with st.spinner("Contacting optimizer API..."):
            try:
                resp = requests.post(
                    f"{st.session_state.get('api_url', api_url).rstrip('/')}/optimize",
                    json={"items": items, "stores": selected_stores},
                    timeout=60,
                )
            except requests.RequestException as exc:
                st.error(f"Could not reach optimizer API: {exc}")
                st.session_state["analysis_result"] = {"error": "API request failed"}
                resp = None

        if resp is None:
            pass
        elif resp.status_code != 200:
            st.error(f"Optimizer API error: {resp.status_code} — {resp.text}")
            st.session_state["analysis_result"] = {"error": "Optimizer API returned an error"}
        else:
            data = resp.json()
            warnings = data.get("warnings", [])
            for w in warnings:
                st.warning(w)

            if not data.get("cart"):
                st.session_state["analysis_result"] = {"error": "Could not find a valid combination."}
            else:
                st.session_state["analysis_result"] = {
                    "cart": data.get("cart"),
                    "score": data.get("total_score"),
                    "info": data.get("info"),
                    "all_products": data.get("all_products", {}),
                    "grocery_list": dict(st.session_state["grocery_list"]),
                    "selected_stores": selected_stores,
                }

# =============================================================================
# MAIN — hierarchical product catalog
# =============================================================================

st.subheader("📋 Product Catalog")
st.caption(
    "Open a category, tick the products you need, then adjust quantity and minimum size. "
    "Your selections appear in the sidebar."
)

for category, products in PRODUCT_CATALOG.items():
    with st.expander(category, expanded=False):
        for product_name in products:
            in_list = product_name in st.session_state["grocery_list"]
            checked = st.checkbox(
                f"**{product_name}**",
                value=in_list,
                key=f"chk_{category}_{product_name}",
            )

            if checked:
                # Initialise with sensible defaults on first selection
                if product_name not in st.session_state["grocery_list"]:
                    st.session_state["grocery_list"][product_name] = {
                        "search_term": product_name,
                        "include": [product_name],
                        "exclude": [],
                        "unit": "g",
                        "user_min": 0,
                        "qty": 1,
                        "extra_include": "",
                        "extra_exclude": "",
                    }

                spec = st.session_state["grocery_list"][product_name]
                unit = spec["unit"]

                c1, c2, c3, c4 = st.columns([1, 2, 3, 3])

                qty = c1.number_input(
                    "Quantity",
                    min_value=1,
                    max_value=50,
                    value=spec["qty"],
                    key=f"qty_{category}_{product_name}",
                )
                min_size = c2.number_input(
                    f"Min size ({unit})",
                    min_value=0,
                    value=int(spec["user_min"]),
                    step=50 if unit in ("g", "ml") else 1,
                    key=f"min_{category}_{product_name}",
                )
                extra_inc = c3.text_input(
                    "Prefer keywords (comma-separated)",
                    value=spec["extra_include"],
                    key=f"inc_{category}_{product_name}",
                    placeholder="e.g. täispiim, mahe",
                )
                extra_exc = c4.text_input(
                    "Avoid keywords (comma-separated)",
                    value=spec["extra_exclude"],
                    key=f"exc_{category}_{product_name}",
                    placeholder="e.g. laktoosivaba, madala rasvasisaldusega",
                )

                # Write edits back to session state immediately
                spec["qty"] = qty
                spec["user_min"] = min_size
                spec["extra_include"] = extra_inc
                spec["extra_exclude"] = extra_exc

            elif not checked and product_name in st.session_state["grocery_list"]:
                del st.session_state["grocery_list"][product_name]

# =============================================================================
# RESULTS
# =============================================================================

if st.session_state["analysis_result"]:
    res = st.session_state["analysis_result"]
    st.markdown("---")

    if "error" in res:
        st.error(res["error"])
    else:
        all_products = res["all_products"]
        cart = res["cart"]
        stores = res["selected_stores"]
        gl = res["grocery_list"]

        # ── Store comparison ──────────────────────────────────────────────────
        st.subheader("📊 Store Comparison")
        rows = []
        for store in stores:
            total = 0.0
            missing_count = 0
            for name in gl:
                candidates = [p for p in all_products.get(name, []) if p["store"] == store]
                if candidates:
                    best = min(candidates, key=lambda p: p["score"])
                    total += best["price"]
                else:
                    missing_count += 1
            rows.append({
                "Store": store.capitalize(),
                "Total (€)": round(total, 2),
                "Missing items": missing_count,
            })
        df_stores = pd.DataFrame(rows)
        st.dataframe(df_stores, hide_index=True)

        complete = df_stores[df_stores["Missing items"] == 0]
        if not complete.empty:
            best_row = complete.loc[complete["Total (€)"].idxmin()]
            st.info(f"💡 Best single store: **{best_row['Store']}** — {best_row['Total (€)']:.2f} €")
        elif len(stores) > 1:
            st.warning("No single store has all items. The optimizer may split across stores.")

        # ── Top candidates per item ───────────────────────────────────────────
        st.subheader("🔍 Top candidates per item")
        for name in gl:
            spec = gl[name]
            st.markdown(f"**{name}**")
            prods = sorted(all_products.get(name, []), key=lambda p: p["score"])[:8]
            if prods:
                table_rows = []
                for p in prods:
                    e = p.get("explanation", {})
                    table_rows.append({
                        "Product": p["name"],
                        "Store": p["store"],
                        "Price (€)": round(p["price"], 2),
                        f"Unit price (€/{e.get('unit_label','unit')})": e.get("unit_price", "—"),
                        "Detected size": f"{e.get('size', '?')} {spec.get('unit','?')}",
                        "Relevance": e.get("relevance", "—"),
                        "Size penalty": e.get("size_penalty", "—"),
                        "Final score": e.get("final_score", "—"),
                    })
                st.dataframe(pd.DataFrame(table_rows), hide_index=True, use_container_width=True)
            else:
                st.write("No candidates found.")
            st.markdown("---")

        # ── Best cart ─────────────────────────────────────────────────────────
        st.subheader("✅ Best cart")
        total_price = 0.0
        for p in cart:
            e = p.get("explanation", {})
            item_spec = gl.get(p["item"], {})
            unit = item_spec.get("unit", "g")
            st.markdown(
                f"**{p['item']}** → {p['name']} ({p['store']})  \n"
                f"Price: **{p['price']:.2f} €** · "
                f"Size: {e.get('size', '?')} {unit} · "
                f"Unit price: {e.get('unit_price', '?')} €/{e.get('unit_label','unit')} · "
                f"Score: {e.get('final_score', '?')}"
            )
            total_price += p["price"]

        st.markdown("---")
        st.markdown(f"### 🧾 Total: {total_price:.2f} €")
