import threading
from contextlib import asynccontextmanager

import hmac
import re

from fastapi import FastAPI, Header, HTTPException, Response
from fastapi.responses import RedirectResponse
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from typing import List, Dict, Any, Optional
from core import catalog
from core import editions
from core import my_dinners
from core import events
from core import fetch
from core import mailerlite
from core import plans
from core import recipe_import
from stores_config import dinner_stores, public as stores_public

import io
import os
import time
import uuid
import zipfile
from urllib.parse import urlparse


# Stores with ingredient rules in data/rules.yaml (stores_config.py).
DINNER_STORES = dinner_stores()


def _keep_cache_warm():
    """Load the store answers saved before the restart, then fetch every ingredient rule's searches that
    aren't fresh, and all of them again before the cache expires (about 130 store requests each time).
    Set CACHE_WARMUP=0 to turn it off."""
    print(f"loaded {fetch.load_saved_searches()} saved store searches")
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
    events.flush(timeout=5)  # a restart shouldn't lose the events still queued


app = FastAPI(title="pantryrun API", lifespan=lifespan)
app.add_middleware(GZipMiddleware, minimum_size=1000)


class DinnerRef(BaseModel):
    id: str
    servings: int = 2


class BasketRequest(BaseModel):
    recipe_id: Optional[str] = None
    servings: int = 2
    recipes: List[DinnerRef] = []  # several dinners in one trip; recipe_id is one
    items: List[str] = []
    # {ingredient key or "text:<item>": {"products": {store: name}, "words": [...]}}
    prefs: Dict[str, Any] = {}
    stores: List[str] = DINNER_STORES
    user_id: Optional[str] = None
    session_id: Optional[str] = None
    name: Optional[str] = None  # only to tell internal people apart; not stored


class MyDinnerRequest(BaseModel):
    user_id: str
    name: str
    servings: int = 2
    items: List[str]
    method: Optional[str] = None  # how to cook it
    link: Optional[str] = None    # a recipe page
    image: Optional[str] = None   # its photo (from a recipe link)
    from_share: Optional[str] = None  # link token, when saved from a dinner someone sent
    from_dinner: Optional[str] = None  # the dinner it's a copy of ("Make it yours", WEB-38)


class ShareRequest(BaseModel):
    recipe_id: str
    user_id: Optional[str] = None


class RecipeImportRequest(BaseModel):
    url: str
    user_id: Optional[str] = None


class NewsletterRequest(BaseModel):
    email: str
    consent: bool = False
    user_id: Optional[str] = None
    name: Optional[str] = None
    where: Optional[str] = None  # where in the app: first_visit, footer or get_it (receipt before Oct 2026)


class EditionRequest(BaseModel):
    title: str
    dinners: List[str]
    featured: Optional[str] = None
    featured_url: Optional[str] = None
    servings: int = 2


class EventRequest(BaseModel):
    type: str
    data: Dict[str, Any] = {}
    user_id: Optional[str] = None
    session_id: Optional[str] = None
    name: Optional[str] = None  # only to tell internal people apart; not stored


@app.post("/events")
def log_event(req: EventRequest):
    """Record a user action from the web app (e.g. accepted/rejected a recommendation)."""
    ok = events.log_event(req.type, req.data, user_id=req.user_id, session_id=req.session_id, name=req.name)
    return {"logged": ok}


@app.get("/recipes")
def recipes():
    """Dinners the app can recommend: the hand-written classics, plus store recipes by category (NutriData dishes
    until data/store_recipes.yaml exists), each with what its card shows; and the stores, as the page names them
    (stores_config.py)."""
    data, store = catalog.load_recipes(), catalog.load_store_recipes()
    dishes = store if store["dinners"] else {**catalog.load_dishes(), "dinners": catalog.load_dishes()["dishes"]}
    shown = lambda r: {"id": r["id"], "name": r["name"], "minutes": r.get("minutes"), "about": r.get("about"),
                       "count": len(r["ingredients"]), "photo": _thumb(r.get("image"))}
    return {
        **stores_public(),
        "recipes": [{**shown(r), "emoji": r.get("emoji", "🍽️")} for r in data["recipes"]],
        "categories": dishes["categories"],
        "dishes": [{**shown(d), "category": d["category"]} for d in dishes["dinners"]],
    }


def _thumb(url):
    """A card-sized photo: Rimi's image service makes one from the same address (1200×675 → 480×320)."""
    if url and "res.cloudinary.com/rimibaltic-web/" in url:
        return re.sub(r"/image/upload/[^/]*,[^/]*/", "/image/upload/b_white,c_fill,f_auto,h_320,q_auto,w_480/", url, count=1)
    return url


@app.post("/basket")
def basket(req: BasketRequest):
    """One store for a dinner (optional) plus extra items, honouring the user's preferences.

    Every store's basket is returned (best first), each line with its acceptable alternatives.
    The answer's result_id is logged with it; the web app sends it back with accept, reject, view_store and
    wrong_product, so those can be joined to the answer they were about.
    """
    if not req.recipe_id and not req.recipes and not any(i.strip() for i in req.items):
        raise HTTPException(status_code=400, detail="Pick a recipe or add at least one item")
    if len(req.recipes) > catalog.MAX_DINNERS:
        raise HTTPException(status_code=400, detail=f"At most {catalog.MAX_DINNERS} dinners in one trip")
    # One request can't make the server search the stores thousands of times (a store could block it).
    if len([i for i in req.items if i.strip()]) > my_dinners.MAX_ITEMS:
        raise HTTPException(status_code=400, detail=f"At most {my_dinners.MAX_ITEMS} items in one list")
    stores = [s for s in dict.fromkeys(req.stores) if s in DINNER_STORES]  # known stores, each once
    if not stores:
        raise HTTPException(status_code=400, detail="No known store")
    people = lambda n: max(1, min(n, 12))
    dinners = [{"id": d.id, "servings": people(d.servings)} for d in req.recipes]
    started = time.monotonic()
    try:
        result = catalog.recommend(req.recipe_id, people(req.servings), req.items, stores, req.prefs,
                                   user_id=req.user_id, dinners=dinners)
    except KeyError as e:
        raise HTTPException(status_code=404, detail=f"Unknown recipe: {e.args[0]}")
    result["result_id"] = uuid.uuid4().hex
    events.log_event(
        "basket",
        {
            "result_id": result["result_id"],
            "mission": "dinners" if len(result["dinners"]) > 1 else "dinner" if result["dinners"] else "list",
            "recipe_id": result["recipe"]["id"] if result["recipe"] else None,
            "recipe_ids": [d["id"] for d in result["dinners"]],
            "dinner_count": len(result["dinners"]),
            "servings": result["servings"],
            "items": result["items"],
            "prefs": req.prefs,
            "stores": stores,
            "latency_s": round(time.monotonic() - started, 2),
            "recommended_store": result["store"],
            "baskets": [
                {"store": b["store"], "status": b["status"], "total_price": b["total_price"], "missing": b["missing"],
                 "chosen": {l["key"]: l["product"] for l in b["lines"]}}
                for b in result["baskets"]
            ],
        },
        user_id=req.user_id,
        session_id=req.session_id,
        name=req.name,
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
        dinner = my_dinners.save(req.user_id, req.name, req.servings, req.items, dinner_id, req.method, req.link,
                                 req.image)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    if dinner is None:
        raise HTTPException(status_code=404, detail="No such dinner")
    events.log_event("my_dinner_saved", {"id": dinner["id"], "new": dinner_id is None, "items": len(dinner["items"]),
                                         "method": bool(dinner["method"]), "link": bool(dinner["link"]),
                                         "from_share": req.from_share, "from_dinner": req.from_dinner},
                     user_id=req.user_id)
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


@app.get("/recipes/{recipe_id}/card")
def recipe_card(recipe_id: str, servings: int = 2, user_id: Optional[str] = None):
    """A dinner's recipe card for its own page: ingredients for this many people, method, link, photo.
    No store is asked, so it's instant."""
    found = catalog.recipe_card(recipe_id, max(1, min(servings, 12)), user_id)
    if found is None:
        raise HTTPException(status_code=404, detail="No such dinner")
    return found


@app.get("/recipes/{recipe_id}/copy")
def copy_recipe(recipe_id: str, user_id: Optional[str] = None):
    """Any dinner (a classic, a NutriData dish, one sent by link) as typed items, to change and save as one's own
    ("Make it yours"). Nothing is saved here."""
    recipes = catalog.load_recipes()
    recipe = catalog.find_recipe(recipe_id, recipes, user_id)
    if recipe is None:
        raise HTTPException(status_code=404, detail="No such dinner")
    return {"from": recipe_id, "name": recipe["name"], "servings": recipe.get("servings", catalog.BASE_SERVINGS),
            "items": catalog.recipe_as_items(recipe, recipes),
            **{k: recipe.get(k) or "" for k in ("method", "link", "image")}}


@app.post("/recipe-import")
def import_recipe(req: RecipeImportRequest):
    """A recipe page read into a dinner to check and save: name, servings, what to buy, photo, link.
    Nothing is saved here; the method stays on the page (the dinner keeps the link)."""
    try:
        found = recipe_import.import_recipe(req.url[:1000])
    except recipe_import.PageError as exc:
        events.log_event("recipe_import", {"ok": False, "reason": str(exc)}, user_id=req.user_id)
        raise HTTPException(status_code=422, detail=str(exc))
    events.log_event("recipe_import", {"ok": True, "host": urlparse(found["link"]).hostname, "items": len(found["items"]),
                                       "partial": found["partial"], "image": bool(found["image"])}, user_id=req.user_id)
    return found


@app.post("/shares")
def create_share(req: ShareRequest):
    """A link to send a dinner to someone: a snapshot of it, priced for whoever opens it."""
    recipes = catalog.load_recipes()
    recipe = catalog.find_recipe(req.recipe_id, recipes, req.user_id)
    if recipe is None:
        raise HTTPException(status_code=404, detail="No such dinner")
    token = my_dinners.share(req.user_id, req.recipe_id, recipe["name"], recipe.get("servings", catalog.BASE_SERVINGS),
                             catalog.recipe_as_items(recipe, recipes), recipe.get("pantry", []),
                             recipe.get("method"), recipe.get("link"), recipe.get("image"))
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


@app.post("/newsletter")
def newsletter_signup(req: NewsletterRequest):
    """Sign-up for next week's plan by email. The address goes to MailerLite only, which asks the person to confirm."""
    email = req.email.strip()
    if not mailerlite.EMAIL.match(email) or len(email) > 200:
        raise HTTPException(status_code=400, detail="That doesn't look like an email address.")
    if not req.consent:
        raise HTTPException(status_code=400, detail="Tick the box to say we may email you.")
    if not req.user_id or not mailerlite.configured():
        raise HTTPException(status_code=503, detail="Sign-up isn't open yet. Try again in a few days.")
    where = req.where if req.where in ("first_visit", "footer", "get_it", "receipt") else None
    try:
        mailerlite.subscribe(email, req.user_id, (req.name or "").strip()[:40] or None)
    except mailerlite.MailerLiteError as exc:
        print(f"newsletter sign-up failed: {exc}")
        events.log_event("newsletter_signup", {"ok": False, "where": where}, user_id=req.user_id, name=req.name)
        raise HTTPException(status_code=502, detail="Couldn't sign you up just now. Try again later.")
    events.log_event("newsletter_signup", {"ok": True, "where": where}, user_id=req.user_id, name=req.name)
    return {"ok": True}


@app.get("/plans/{token}")
def open_plan(token: str, user_id: Optional[str] = None, came_from: Optional[str] = None):
    """A weekly plan's dinners, to load as one trip. Dinners sent by link come whole (the app doesn't know
    them); the others are ids from /recipes. A dinner that no longer exists is left out."""
    plan = plans.get(token)
    if plan is None:
        raise HTTPException(status_code=404, detail="This link doesn't lead to a plan")
    recipes, dinners = catalog.load_recipes(), []
    for rid in plan["dinners"]:
        if rid.startswith("sh-"):
            shared = my_dinners.shared(rid[3:])
            if shared:
                dinners.append({**shared, "featured": rid == plan["featured"]})
        elif catalog.find_recipe(rid, recipes):
            dinners.append({"id": rid, "featured": rid == plan["featured"]})
    events.log_event("plan_opened", {"plan": token, "from": came_from}, user_id=user_id)
    return {"token": plan["token"], "title": plan["title"], "dinners": dinners}


def _owner(authorization):
    """Only the owner runs the newsletter (scripts/weekly_plan.py): EDITION_TOKEN, sent as a bearer token."""
    secret = os.environ.get("EDITION_TOKEN")
    if not secret:
        raise HTTPException(status_code=503, detail="EDITION_TOKEN isn't set on the server")
    if not hmac.compare_digest(authorization or "", f"Bearer {secret}"):
        raise HTTPException(status_code=401, detail="Wrong EDITION_TOKEN")


def _edition_step(step):
    try:
        return step()
    except editions.EditionError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    except mailerlite.MailerLiteError as exc:
        raise HTTPException(status_code=502, detail=f"MailerLite: {exc}")


@app.post("/editions")
def make_edition(req: EditionRequest, authorization: Optional[str] = Header(None)):
    """A weekly plan edition, priced here (stores answer this server). Each one searches every store."""
    _owner(authorization)
    return _edition_step(lambda: editions.make(req.title, req.dinners, req.featured, req.featured_url,
                                               max(1, min(req.servings, 12))))


@app.post("/editions/promote")
def promote_subscribers(authorization: Optional[str] = Header(None)):
    """Before an edition: subscribers past their first week join the group it's sent to."""
    _owner(authorization)
    return _edition_step(editions.promote)


@app.post("/editions/{token}/sent")
def edition_sent(token: str, authorization: Optional[str] = Header(None)):
    """After an edition: log it as a reminder for everyone it went to."""
    _owner(authorization)
    return _edition_step(lambda: editions.record_sent(token))


@app.get("/cooked")
def cooked(plan: str, dinner: str, answer: str = "yes", u: Optional[str] = None):
    """The one-tap "Did you cook it?" links in a newsletter edition: log the answer, then say thanks."""
    if answer in ("yes", "no"):
        events.log_event("cooked", {"plan": plan[:20], "dinner": dinner[:40], "answer": answer}, user_id=u)
    return RedirectResponse("/thanks.html", status_code=303)


@app.get("/health")
def health():
    return {"status": "ok"}


_EXTENSION = os.path.join(os.path.dirname(os.path.dirname(__file__)), "extension")


@app.get("/extension.zip")
def extension_zip():
    """pantryrun's Rimi cart extension (extension/), zipped to load unpacked in Chrome or Edge."""
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        for name in sorted(os.listdir(_EXTENSION)):
            z.write(os.path.join(_EXTENSION, name), f"pantryrun-rimi/{name}")
    return Response(buf.getvalue(), media_type="application/zip",
                    headers={"Content-Disposition": 'attachment; filename="pantryrun-rimi-extension.zip"'})


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
