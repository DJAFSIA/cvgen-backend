import logging
from fastapi import FastAPI, Request
from sqlalchemy import text
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from app.core.config import settings
from app.core.database import SessionLocal
from app.routers import auth, profil, offre, candidature, billing, compte
from app.services.ia_service import IAError

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
logger = logging.getLogger("cvgen")

PRODUCTION = settings.ENV == "production"
if PRODUCTION:
    erreurs = settings.verifier_production()
    if erreurs:
        raise RuntimeError("Configuration de production invalide :\n- " + "\n- ".join(erreurs))

app = FastAPI(
    title="CVGen API",
    description="API de génération intelligente de CV et lettres de motivation",
    version="1.0.0",
    # Documentation interactive masquee en production
    docs_url=None if PRODUCTION else "/docs",
    redoc_url=None if PRODUCTION else "/redoc",
    openapi_url=None if PRODUCTION else "/openapi.json",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


app.include_router(auth.router, prefix="/auth", tags=["Authentification"])
app.include_router(profil.router, prefix="/profil", tags=["Profil"])
app.include_router(offre.router, prefix="/offre", tags=["Offres"])
app.include_router(candidature.router, prefix="/candidature", tags=["Candidatures"])
app.include_router(billing.router, prefix="/billing", tags=["Abonnement"])
app.include_router(compte.router, prefix="/compte", tags=["Compte et donnees personnelles"])

@app.exception_handler(IAError)
async def ia_error_handler(request: Request, exc: IAError):
    logger.warning("Erreur IA sur %s: %s", request.url.path, exc)
    return JSONResponse(
        status_code=502,
        content={"detail": {"code": "ia_unavailable", "message": "Le service d'IA est momentanement indisponible, reessayez dans un instant."}},
    )


@app.get("/")
def root():
    return {"message": "CVGen API opérationnelle"}


@app.get("/health", include_in_schema=False)
def health():
    """Sonde de l'hebergeur : l'API repond et la base de donnees est joignable."""
    try:
        with SessionLocal() as db:
            db.execute(text("SELECT 1"))
    except Exception:
        logger.exception("Base de donnees injoignable")
        return JSONResponse(status_code=503, content={"status": "error", "db": False})
    return {"status": "ok", "db": True}
