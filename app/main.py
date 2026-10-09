import logging
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from app.core.config import settings
from app.routers import auth, profil, offre, candidature, billing
from app.services.ia_service import IAError

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
logger = logging.getLogger("cvgen")

app = FastAPI(
    title="CVGen API",
    description="API de génération intelligente de CV et lettres de motivation",
    version="1.0.0"
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
