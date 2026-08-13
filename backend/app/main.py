from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.sessions import SessionMiddleware

from app.database import Base, engine
from app import models  # noqa: F401 — ensures models are registered before create_all
from app.config import settings
from app.routers import auth, people, cards, documents, reminders, search, share, audit, backup
from app import admin

Base.metadata.create_all(bind=engine)

app = FastAPI(
    title="Health Vault API",
    description="Backend for the Health Vault app — hospital cards, medical documents, "
                "family member profiles, and reminders. Runs on the Pi.",
    version="1.0.0",
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
app.include_router(admin.router)


@app.get("/health")
def health():
    return {"status": "ok"}
