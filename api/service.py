from fastapi import FastAPI
from pydantic import BaseModel
from typing import List, Dict, Any
from core import fetch as core_fetch
from core import optimiser

import os
import threading
import time
import json
import re
from difflib import SequenceMatcher
from catalog.generate_catalog import generate_catalog


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


class AvailabilityRequest(BaseModel):
    items: List[str]
    stores: List[str] = ["rimi", "selver", "barbora"]


def _load_normalized_catalog():
    path = os.path.join(os.path.dirname(__file__), "..", "catalog", "normalized_catalog.json")
    path = os.path.normpath(path)
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return []


@app.get("/search_catalog")
def search_catalog(q: str = "", limit: int = 10):
    """Search normalized_catalog.json for best human-friendly suggestions.

    Behavior goals:
    - If the user types a single token (e.g. "paprika", "kartul"), prefer
      whole-word matches in the product name or the `macro` field and do NOT
      match that token inside longer words (avoid 'riis' -> 'riisnuudlid').
    - If the query has multiple tokens, use token-overlap + sequence ratio.
    - Strongly boost matches where the `macro` contains the query token(s).
    - Return the top N friendly suggestions (default 5 for quick-add UX).
    """
    if not q:
        return {"results": []}
    ql = q.lower().strip()
    data = _load_normalized_catalog()

    def _is_size_token(t: str) -> bool:
        return re.fullmatch(r"\d+(?:[.,]\d+)?(?:g|kg|ml|l)?", t) is not None

    q_tokens = [t for t in re.findall(r"\w+", ql) if len(t) > 1 and not _is_size_token(t)]
    q_token_set = set(q_tokens)
    is_single = len(q_token_set) == 1

    candidates = []
    for rec in data:
        name = rec.get("name", "")
        nl = name.lower()
        macro = (rec.get("macro") or "")
        macro_l = macro.lower()

        name_tokens = set([t for t in re.findall(r"\w+", nl) if len(t) > 1 and not _is_size_token(t)])
        macro_tokens = set([t for t in re.findall(r"\w+", macro_l) if len(t) > 1 and not _is_size_token(t)])

        # Single-token queries: only consider records where the token appears as
        # a whole word in the product name or in the macro.
        if is_single and q_token_set:
            t = list(q_token_set)[0]
            if (t not in name_tokens) and (t not in macro_tokens) and (macro_l != t):
                continue

        # For multi-token queries, require at least one token overlap OR the
        # full query substring to appear in the product name; otherwise skip.
        if (not is_single) and q_token_set:
            if len(q_token_set & name_tokens) == 0 and len(q_token_set & macro_tokens) == 0 and ql not in nl:
                continue

        # Scoring: macro matches get a stronger boost, name token overlap next,
        # and sequence matcher is a soft fallback.
        # support fuzzy token matching for near-miss spelling (e.g. jasmiin -> jasmiini)
        def _token_matches(qt, token_set):
            if qt in token_set:
                return True
            for tt in token_set:
                if SequenceMatcher(None, qt, tt).ratio() >= 0.8:
                    return True
            return False

        match_count_name = sum(1 for qt in q_token_set if _token_matches(qt, name_tokens)) if q_token_set else 0
        match_count_macro = sum(1 for qt in q_token_set if _token_matches(qt, macro_tokens)) if q_token_set else 0
        name_overlap = match_count_name / max(1, len(q_token_set)) if q_token_set else 0.0
        macro_overlap = match_count_macro / max(1, len(q_token_set)) if q_token_set else 0.0
        seq_ratio = SequenceMatcher(None, ql, nl).ratio()

        score = 0.0
        # exact full-string match -> highest score
        if ql == nl:
            score = 2.0
        else:
            score = macro_overlap * 2.0 + name_overlap * 1.0 + seq_ratio * 0.1
            # small bonus for substring (useful for multi-word queries)
            if ql in nl:
                score += 0.4

        # Keep candidates with any meaningful score; we'll sort and trim below.
        if score > 0.15:
            rec2 = dict(rec)
            rec2["_score"] = round(score, 3)
            rec2["macro"] = rec.get("macro")
            candidates.append((score, rec2))

    candidates.sort(key=lambda x: x[0], reverse=True)
    # For quick-add UX we prefer a short list — return up to 5 unless user asked
    # for more explicitly via `limit`.
    max_results = min(5, max(1, int(limit)))
    results = []
    for s, r in candidates[:max_results]:
        results.append({"name": r.get("name"), "category": r.get("category"), "macro": r.get("macro"), "score": round(s, 2)})
    return {"results": results}


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


# Optional background generation: enable by setting AUTO_GENERATE_CATALOG=1
def _catalog_generator_loop(interval_hours: int = 24):
    interval = max(1, int(interval_hours)) * 3600
    while True:
        try:
            print("[catalog] Running scheduled generate_catalog()")
            generate_catalog()
        except Exception as exc:
            print(f"[catalog] Auto-generation failed: {exc}")
        time.sleep(interval)


@app.on_event("startup")
def _maybe_start_catalog_generator():
    if os.environ.get("AUTO_GENERATE_CATALOG") == "1":
        try:
            hours = int(os.environ.get("AUTO_GENERATE_INTERVAL_HOURS", "24"))
        except Exception:
            hours = 24
        t = threading.Thread(target=_catalog_generator_loop, args=(hours,), daemon=True)
        t.start()
