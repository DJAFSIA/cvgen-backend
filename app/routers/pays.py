"""Pays dont Apply connait les usages du CV et de la lettre (fiches de app/pays)."""
from fastapi import APIRouter

from app.pays import fiches

router = APIRouter()


@router.get("/")
def liste_pays():
    """Fiches resumees pour le choix du pays vise : nom, points cles, fiabilite, sources, date."""
    return [
        {
            "code": f.code,
            "nom": f.nom,
            "resume": f.resume,
            "pages_max": f.pages_max,
            "photo": f.photo,
            "etat_civil": f.etat_civil.model_dump(),
            "fiabilite": f.fiabilite,
            "sources": [s.model_dump(mode="json") for s in f.sources],
            "verifie_le": f.verifie_le.isoformat(),
        }
        for f in fiches().values()
    ]
