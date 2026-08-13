from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from starlette.middleware.sessions import SessionMiddleware

from app.database import engine, SessionLocal
from app.config import settings
from app.schema import ensure_schema
from app.routers import auth, people, cards, documents, reminders, search, share, audit, backup, labs, health, storage, vault
from app import admin, models

# First run: create every table. Existing Pi DB: add any columns the old file is missing.
ensure_schema(engine)

app = FastAPI(
    title="Vault API",
    description="Self-hosted vault: Health Vault (medical records) and Password Vault "
                "(logins, notes, cards, identities). Runs on the Pi.",
    version="1.1.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Session cookie support for the /admin web UI (separate from the JWT-based
# mobile API auth). Uses the same secret as JWT signing — fine since these
# cookies never leave the browser and are httponly by default.
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
app.include_router(admin.router)

_static = Path(__file__).resolve().parent / "static"
_static.mkdir(exist_ok=True)
app.mount("/static", StaticFiles(directory=str(_static)), name="static")
_templates = Jinja2Templates(directory=str(Path(__file__).resolve().parent / "templates"))


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
