"""Usages du CV et de la lettre par pays (fiches JSON de app/pays/fiches).

Chaque fiche donne les regles d'un pays, ses sources et sa date de verification. Elles sont
injectees dans les consignes de l'IA (comme la langue des documents) ; le pays vise est detecte
dans l'offre puis modifiable par l'utilisateur. Une fiche est une donnee : une mise a jour se fait
en modifiant le JSON, apres verification des sources.
"""
from __future__ import annotations

import json
from datetime import date
from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field, HttpUrl

DOSSIER = Path(__file__).parent / "fiches"
AUTRE = "autre"  # pays hors liste ou non indique : format international, sans fiche

Usage = Literal["attendue", "facultative", "deconseillee"]


class EtatCivil(BaseModel):
    date_naissance: Usage
    nationalite: Usage
    situation_familiale: Usage


class Source(BaseModel):
    titre: str
    url: HttpUrl
    type: Literal["officielle", "privee"]


class FichePays(BaseModel):
    code: str = Field(pattern=r"^[a-z]{2}(-[a-z]{2})?$")
    nom: dict[Literal["fr", "en"], str]
    langues_usuelles: list[str] = Field(min_length=1)
    pages_max: int = Field(ge=1, le=3)
    photo: Usage
    etat_civil: EtatCivil
    regles_cv: list[str] = Field(min_length=3)
    regles_lettre: list[str] = Field(min_length=1)
    resume: dict[Literal["fr", "en"], list[str]]
    # officielle : au moins une source publique (Etat, agence pour l'emploi) ; usage : guides prives
    fiabilite: Literal["officielle", "usage"]
    sources: list[Source] = Field(min_length=1)
    verifie_le: date


@lru_cache
def fiches() -> dict[str, FichePays]:
    """Toutes les fiches, validees, par code de pays."""
    toutes = [FichePays.model_validate(json.loads(p.read_text(encoding="utf-8"))) for p in sorted(DOSSIER.glob("*.json"))]
    par_code = {f.code: f for f in toutes}
    if len(par_code) != len(toutes):
        raise ValueError("Deux fiches pays ont le meme code")
    return par_code


def codes() -> list[str]:
    return list(fiches())


def fiche(code: str | None) -> FichePays | None:
    """La fiche d'un pays, ou None pour « autre », un code vide ou inconnu."""
    return fiches().get(code or "")


_DONNEES_PERSO = (
    "Donnees personnelles : n'ajoute ni photo, ni date de naissance, ni nationalite, ni situation familiale "
    "si le profil ne les fournit pas ; n'en invente jamais."
)


def consigne_cv(f: FichePays | None) -> str:
    """Bloc a ajouter aux regles du prompt du CV (vide sans fiche)."""
    if f is None:
        return ""
    lignes = [
        f"- Usages du pays vise, {f.nom['fr']} (a appliquer sans enfreindre les regles precedentes) :",
        f"  - {f.pages_max} page{'s' if f.pages_max > 1 else ''} au plus.",
        *(f"  - {r}" for r in f.regles_cv),
        f"  - {_DONNEES_PERSO}",
    ]
    return "\n".join(lignes)


def consigne_lettre(f: FichePays | None) -> str:
    """Bloc a ajouter aux regles du prompt de la lettre (vide sans fiche)."""
    if f is None:
        return ""
    return "\n".join([f"- Usages du pays vise, {f.nom['fr']} :", *(f"  - {r}" for r in f.regles_lettre)])


def liste_pour_detection() -> str:
    """Codes et noms des pays, pour demander a l'IA le pays du poste."""
    return ", ".join(f"{f.code} ({f.nom['fr']})" for f in fiches().values())
