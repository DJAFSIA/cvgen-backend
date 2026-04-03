from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.routers import auth, profil, offre, candidature

app = FastAPI(
    title="CVGen API",
    description="API de génération intelligente de CV et lettres de motivation",
    version="1.0.0"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth.router, prefix="/auth", tags=["Authentification"])
app.include_router(profil.router, prefix="/profil", tags=["Profil"])
app.include_router(offre.router, prefix="/offre", tags=["Offres"])
app.include_router(candidature.router, prefix="/candidature", tags=["Candidatures"])

@app.get("/")
def root():
    return {"message": "CVGen API opérationnelle"}
