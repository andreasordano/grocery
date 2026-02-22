from fastapi import FastAPI
from pydantic import BaseModel
from typing import List, Dict, Any
from core import fetch as core_fetch
from core import optimiser

app = FastAPI(title="Groceries Optimizer API")


class OptimizeRequest(BaseModel):
    items: List[str]
    stores: List[str] = ["rimi", "selver", "barbora"]


class OptimizeResponse(BaseModel):
    cart: List[Dict[str, Any]]
    total_score: float
    info: Dict[str, Any]
    warnings: List[str]
    all_products: Dict[str, List[Dict[str, Any]]]


@app.get("/health")
def health():
    return {"status": "ok"}


@app.post("/optimize", response_model=OptimizeResponse)
def optimize(req: OptimizeRequest):
    # Build grocery_list spec (use item name as search_term)
    grocery_list = {it: {"search_term": it} for it in req.items}
    all_products, warnings = core_fetch.fetch_all(grocery_list, req.stores)
    cart, total_score, info = optimiser.optimize_cart(all_products, req.items, req.stores)
    # convert defaultdict to regular dict for JSON serialization
    return {"cart": cart, "total_score": total_score, "info": info, "warnings": warnings, "all_products": dict(all_products)}
