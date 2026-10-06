import threading
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from typing import List, Dict, Any, Optional
from core import catalog
from core import my_dinners
from core import events
from core import fetch

import os
import time


# Stores with ingredient rules in data/rules.yaml (Barbora stands in for Maxima).
DINNER_STORES = ["selver", "rimi", "barbora"]


def _keep_cache_warm():
    """Fetch every ingredient rule's searches at startup, then again before the cache expires
    (about 120 store requests each time). Set CACHE_WARMUP=0 to turn it off."""
    refresh = False
    while True:
        started = time.monotonic()
        try:
            catalog.warm_cache(DINNER_STORES, refresh)
            print(f"cache warm-up done in {time.monotonic() - started:.0f} s")
        except Exception as exc:  # never take the service down over it
            print(f"cache warm-up failed: {exc}")
        refresh = True
        time.sleep(fetch._CACHE.ttl * 0.8)


@asynccontextmanager
async def lifespan(app):
    if os.environ.get("CACHE_WARMUP", "1") == "1":
        threading.Thread(target=_keep_cache_warm, name="cache-warmup", daemon=True).start()
    yield


app = FastAPI(title="pantryrun API", lifespan=lifespan)
app.add_middleware(GZipMiddleware, minimum_size=1000)


class BasketRequest(BaseModel):
    recipe_id: Optional[str] = None
    servings: int = 2
    items: List[str] = []
    # {ingredient key or "text:<item>": {"products": {store: name}, "words": [...]}}
    prefs: Dict[str, Any] = {}
    stores: List[str] = DINNER_STORES
    user_id: Optional[str] = None
    session_id: Optional[str] = None


class MyDinnerRequest(BaseModel):
    user_id: str
    name: str
    servings: int = 2
    items: List[str]
    from_share: Optional[str] = None  # link token, when saved from a dinner someone sent


class ShareRequest(BaseModel):
    recipe_id: str
    user_id: Optional[str] = None


class EventRequest(BaseModel):
    type: str
    data: Dict[str, Any] = {}
    user_id: Optional[str] = None
    session_id: Optional[str] = None


@app.post("/events")
def log_event(req: EventRequest):
    """Record a user action from the web app (e.g. accepted/rejected a recommendation)."""
    ok = events.log_event(req.type, req.data, user_id=req.user_id, session_id=req.session_id)
    return {"logged": ok}


@app.get("/recipes")
def recipes():
    """Dinners the app can recommend: the hand-written classics, plus NutriData dishes by category."""
    data, dishes = catalog.load_recipes(), catalog.load_dishes()
    return {
        "recipes": [{"id": r["id"], "name": r["name"], "emoji": r.get("emoji", "🍽️")} for r in data["recipes"]],
        "categories": dishes["categories"],
        "dishes": [{"id": d["id"], "name": d["name"], "category": d["category"]} for d in dishes["dishes"]],
    }


@app.post("/basket")
def basket(req: BasketRequest):
    """One store for a dinner (optional) plus extra items, honouring the user's preferences.

    Every store's basket is returned (best first), each line with its acceptable alternatives.
    """
    if not req.recipe_id and not any(i.strip() for i in req.items):
        raise HTTPException(status_code=400, detail="Pick a recipe or add at least one item")
    started = time.monotonic()
    try:
        result = catalog.recommend(req.recipe_id, max(1, min(req.servings, 12)), req.items, req.stores, req.prefs,
                                   user_id=req.user_id)
    except KeyError:
        raise HTTPException(status_code=404, detail=f"Unknown recipe: {req.recipe_id}")
    events.log_event(
        "basket",
        {
            "mission": "dinner" if req.recipe_id else "list",
            "recipe_id": req.recipe_id,
            "servings": result["servings"],
            "items": result["items"],
            "prefs": req.prefs,
            "stores": req.stores,
            "latency_s": round(time.monotonic() - started, 2),
            "recommended_store": result["store"],
            "baskets": [
                {"store": b["store"], "total_price": b["total_price"], "missing": b["missing"],
                 "chosen": {l["key"]: l["product"] for l in b["lines"]}}
                for b in result["baskets"]
            ],
        },
        user_id=req.user_id,
        session_id=req.session_id,
    )
    return result


@app.get("/my-dinners")
def list_my_dinners(user_id: str):
    """This person's own dinners (owner = the name in their personal link)."""
    return {"dinners": my_dinners.list_for(user_id)}


def _save_my_dinner(req: MyDinnerRequest, dinner_id: Optional[str] = None):
    if not req.user_id.strip():
        raise HTTPException(status_code=400, detail="Missing user")
    try:
        dinner = my_dinners.save(req.user_id, req.name, req.servings, req.items, dinner_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    if dinner is None:
        raise HTTPException(status_code=404, detail="No such dinner")
    events.log_event("my_dinner_saved", {"id": dinner["id"], "new": dinner_id is None, "items": len(dinner["items"]),
                                         "from_share": req.from_share}, user_id=req.user_id)
    return dinner


@app.post("/my-dinners")
def create_my_dinner(req: MyDinnerRequest):
    return _save_my_dinner(req)


@app.put("/my-dinners/{dinner_id}")
def update_my_dinner(dinner_id: str, req: MyDinnerRequest):
    return _save_my_dinner(req, dinner_id)


@app.delete("/my-dinners/{dinner_id}")
def delete_my_dinner(dinner_id: str, user_id: str):
    if not my_dinners.delete(user_id, dinner_id):
        raise HTTPException(status_code=404, detail="No such dinner")
    events.log_event("my_dinner_deleted", {"id": dinner_id}, user_id=user_id)
    return {"deleted": dinner_id}


@app.post("/shares")
def create_share(req: ShareRequest):
    """A link to send a dinner to someone: a snapshot of it, priced for whoever opens it."""
    recipes = catalog.load_recipes()
    recipe = catalog.find_recipe(req.recipe_id, recipes, req.user_id)
    if recipe is None:
        raise HTTPException(status_code=404, detail="No such dinner")
    token = my_dinners.share(req.user_id, req.recipe_id, recipe["name"], recipe.get("servings", catalog.BASE_SERVINGS),
                             catalog.recipe_as_items(recipe, recipes), recipe.get("pantry", []))
    events.log_event("share_created", {"token": token, "recipe_id": req.recipe_id}, user_id=req.user_id)
    return {"token": token, "path": f"/?dinner={token}"}


@app.get("/shares/{token}")
def open_share(token: str, user_id: Optional[str] = None):
    """The dinner behind a link."""
    dinner = my_dinners.shared(token)
    if dinner is None:
        raise HTTPException(status_code=404, detail="This link doesn't lead to a dinner")
    events.log_event("share_opened", {"token": token}, user_id=user_id)
    return dinner


@app.get("/health")
def health():
    return {"status": "ok"}


class _WebFiles(StaticFiles):
    """The web app: web/index.html at /, and its css/, js/, icon.svg and vocab.json.
    Browsers check back on every load (a quick 304 when nothing changed), so a deploy shows at once.
    The suggestion words (built by scripts/build_vocab.py) change rarely, so they are kept a day."""

    async def get_response(self, path, scope):
        response = await super().get_response(path, scope)
        response.headers["Cache-Control"] = "public, max-age=86400" if path == "vocab.json" else "no-cache"
        return response


# Last, so every API route above is matched first.
app.mount("/", _WebFiles(directory=os.path.join(os.path.dirname(os.path.dirname(__file__)), "web"), html=True), name="web")
