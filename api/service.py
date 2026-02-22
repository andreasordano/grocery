from fastapi import FastAPI
from pydantic import BaseModel
from typing import List, Dict, Any
from core import fetch as core_fetch
from core import optimiser
from stores_config import get_default_stores

import os
import json
import re


app = FastAPI(title="Groceries Optimizer API")

# Get default stores from config
_DEFAULT_STORES = get_default_stores()


class OptimizeRequest(BaseModel):
    items: List[str]
    stores: List[str] = _DEFAULT_STORES


class OptimizeResponse(BaseModel):
    cart: List[Dict[str, Any]]
    total_score: float
    info: Dict[str, Any]
    warnings: List[str]
    all_products: Dict[str, List[Dict[str, Any]]]


class AvailabilityRequest(BaseModel):
    items: List[str]
    stores: List[str] = _DEFAULT_STORES




@app.post("/availability")
def availability(req: AvailabilityRequest):
    """Return availability per item: which stores returned candidates."""
    grocery_list = {it: {"search_term": it} for it in req.items}
    all_products, warnings = core_fetch.fetch_all(grocery_list, req.stores)
    availability = {}
    for it in req.items:
        prods = all_products.get(it, [])
        stores_with = sorted({p["store"] for p in prods})
        availability[it] = stores_with
    return {"availability": availability, "warnings": warnings}


@app.get("/health")
def health():
    return {"status": "ok"}


@app.post("/optimize", response_model=OptimizeResponse)
def optimize(req: OptimizeRequest):
    # Build grocery_list spec (use item name as search_term)
    # Build a richer spec per item: include tokenized keywords so relevance scoring
    # can use keyword matches even when the UI sent only a display name.
    grocery_list = {}
    def _is_size_token(t: str) -> bool:
        return re.fullmatch(r"\d+(?:[.,]\d+)?(?:g|kg|ml|l)?", t) is not None
    for it in req.items:
        it_l = it.lower()
        tokens = [t for t in re.findall(r"\w+", it_l) if len(t) > 1 and not _is_size_token(t)]
        grocery_list[it] = {"search_term": it, "include": tokens}
    all_products, warnings = core_fetch.fetch_all(grocery_list, req.stores)
    cart, total_score, info = optimiser.optimize_cart(all_products, req.items, req.stores)
    # convert defaultdict to regular dict for JSON serialization
    return {"cart": cart, "total_score": total_score, "info": info, "warnings": warnings, "all_products": dict(all_products)}

