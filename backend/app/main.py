from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.middleware.sessions import SessionMiddleware

from app.database import engine, SessionLocal
from app.config import settings
from app.schema import ensure_schema
from app.routers import auth, people, cards, documents, reminders, search, share, audit, backup, labs, health, storage, vault, finance, locker, urls, expense_analyser, ai, tracker, diary
from app.scheduler import lifespan
from app import admin, admin_sa, models
from app.templating import setup_templates

# First run: create every table. Existing Pi DB: add any columns the old file is missing.
ensure_schema(engine)
from app.accounts import ensure_superadmin
ensure_superadmin()


class ModuleAccessMiddleware(BaseHTTPMiddleware):
    """Block /admin module pages when Super Admin disabled them for this vault.

    Must sit inside SessionMiddleware so ``request.session`` is available.
    """

    async def dispatch(self, request: Request, call_next):
        path = request.url.path
        if path.startswith("/admin"):
            from app import modules as mod

            key = mod.admin_module_for_path(path)
            if key:
                user_id = request.session.get("user_id")
                if user_id:
                    db = SessionLocal()
                    try:
                        user = db.query(models.User).filter(models.User.id == user_id).first()
                        if user and not mod.is_enabled(db, user, key):
                            return RedirectResponse("/admin/modules", status_code=302)
                    finally:
                        db.close()
        return await call_next(request)


app = FastAPI(
    title="Vault API",
    description="Self-hosted vault: Health, Passwords, Money Manager, Expense Analyser, Shopping List, AI, Documents, URLs, and Digital Diary.",
    version="1.2.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Inner module gate, then Session outside it (last add_middleware = outermost).
app.add_middleware(ModuleAccessMiddleware)
app.add_middleware(SessionMiddleware, secret_key=settings.JWT_SECRET, session_cookie="healthvault_admin_session")

app.include_router(auth.router)
app.include_router(people.router)
app.include_router(cards.router)
app.include_router(documents.router)
app.include_router(reminders.router)
app.include_router(search.router)
app.include_router(share.router)
app.include_router(audit.router)
app.include_router(backup.router)
app.include_router(labs.router)
app.include_router(health.router)
app.include_router(storage.router)
app.include_router(vault.router)
app.include_router(finance.router)
app.include_router(expense_analyser.router)
app.include_router(ai.router)
app.include_router(locker.router)
app.include_router(tracker.router)
app.include_router(urls.router)
app.include_router(diary.router)
app.include_router(admin.router)
app.include_router(admin_sa.router)

_static = Path(__file__).resolve().parent / "static"
_static.mkdir(exist_ok=True)
app.mount("/static", StaticFiles(directory=str(_static)), name="static")
_templates = setup_templates()


@app.get("/")
def root():
    """Browser visits to the server root should open the web app, not 404."""
    return RedirectResponse("/admin", status_code=302)


@app.get("/health")
def health():
    return {"status": "ok"}


@app.get("/s/{token}")
def short_share(token: str):
    """Short URL for a hospital front-desk browser: /s/<token> → public HTML page."""
    return RedirectResponse(f"/share/public/{token}/page", status_code=302)


@app.get("/p/{token}")
def short_pack(token: str):
    return RedirectResponse(f"/share/public/pack/{token}/page", status_code=302)


@app.get("/v/{token}")
def short_vault_send(token: str):
    return RedirectResponse(f"/vault/public/{token}/page", status_code=302)


@app.get("/u/{token}")
def short_url_share(token: str):
    return RedirectResponse(f"/urls/public/{token}/page", status_code=302)


@app.get("/shop/{token}")
def short_shop_share(token: str):
    return RedirectResponse(f"/tracker/public/{token}/page", status_code=302)


@app.get("/ice/{token}", response_class=HTMLResponse)
def ice_card(token: str, request: Request):
    db = SessionLocal()
    try:
        person = db.query(models.Person).filter(models.Person.ice_token == token).first()
        if not person:
            return HTMLResponse("<h1>Not found</h1>", status_code=404)
        return _templates.TemplateResponse(request, "ice_public.html", {"person": person})
    finally:
        db.close()


@app.get("/manifest.webmanifest")
def pwa_manifest():
    from fastapi.responses import FileResponse
    path = _static / "manifest.webmanifest"
    if path.exists():
        return FileResponse(path, media_type="application/manifest+json")
    return {"name": "Health Vault", "start_url": "/admin", "display": "standalone"}
