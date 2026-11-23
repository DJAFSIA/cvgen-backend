"""Etat civil et photo d'un CV, ajoutes par le serveur au moment de creer le PDF.

Ces donnees (date et lieu de naissance, nationalite, situation familiale, titre de sejour, photo)
ne passent jamais par l'IA : elles sont lues dans le profil, filtrees selon les usages du pays vise
(app/pays) et ecrites dans la langue du document. Rien n'est copie dans le document enregistre :
si la personne les retire de son profil, elles disparaissent aussi de ses prochains telechargements.
"""
from __future__ import annotations

import json
from base64 import b64encode
from datetime import date
from functools import lru_cache
from pathlib import Path

from app.pays import FichePays
from app.schemas.document import Affichage

LANGUES = ("fr", "en", "es", "de", "pt", "it")

_MOIS = {
    "fr": ["janvier", "février", "mars", "avril", "mai", "juin", "juillet", "août", "septembre", "octobre", "novembre", "décembre"],
    "en": ["January", "February", "March", "April", "May", "June", "July", "August", "September", "October", "November", "December"],
    "es": ["enero", "febrero", "marzo", "abril", "mayo", "junio", "julio", "agosto", "septiembre", "octubre", "noviembre", "diciembre"],
    "de": ["Januar", "Februar", "März", "April", "Mai", "Juni", "Juli", "August", "September", "Oktober", "November", "Dezember"],
    "pt": ["janeiro", "fevereiro", "março", "abril", "maio", "junho", "julho", "agosto", "setembro", "outubro", "novembro", "dezembro"],
    "it": ["gennaio", "febbraio", "marzo", "aprile", "maggio", "giugno", "luglio", "agosto", "settembre", "ottobre", "novembre", "dicembre"],
}

_LIBELLES = {
    "fr": {"date_lieu": "Date et lieu de naissance", "date": "Date de naissance", "lieu": "Lieu de naissance", "nationalite": "Nationalité", "situation": "Situation familiale", "permis": "Titre de séjour ou de travail"},
    "en": {"date_lieu": "Date and place of birth", "date": "Date of birth", "lieu": "Place of birth", "nationalite": "Nationality", "situation": "Marital status", "permis": "Residence or work permit"},
    "es": {"date_lieu": "Fecha y lugar de nacimiento", "date": "Fecha de nacimiento", "lieu": "Lugar de nacimiento", "nationalite": "Nacionalidad", "situation": "Estado civil", "permis": "Permiso de residencia o de trabajo"},
    "de": {"date_lieu": "Geburtsdatum und -ort", "date": "Geburtsdatum", "lieu": "Geburtsort", "nationalite": "Staatsangehörigkeit", "situation": "Familienstand", "permis": "Aufenthalts- oder Arbeitsbewilligung"},
    "pt": {"date_lieu": "Data e local de nascimento", "date": "Data de nascimento", "lieu": "Local de nascimento", "nationalite": "Nacionalidade", "situation": "Estado civil", "permis": "Autorização de residência ou de trabalho"},
    "it": {"date_lieu": "Data e luogo di nascita", "date": "Data di nascita", "lieu": "Luogo di nascita", "nationalite": "Nazionalità", "situation": "Stato civile", "permis": "Permesso di soggiorno o di lavoro"},
}

# Situation familiale : code de base, puis accord choisi par la personne (_m, _f) ou aucun (forme neutre)
SITUATIONS = ("celibataire", "marie", "marie_m", "marie_f", "pacse", "pacse_m", "pacse_f",
              "divorce", "divorce_m", "divorce_f", "veuf", "veuf_m", "veuf_f")
_SITUATIONS = {  # langue -> code de base -> (neutre, masculin, feminin)
    "fr": {"celibataire": ("Célibataire",) * 3, "marie": ("Marié(e)", "Marié", "Mariée"), "pacse": ("Pacsé(e)", "Pacsé", "Pacsée"),
           "divorce": ("Divorcé(e)", "Divorcé", "Divorcée"), "veuf": ("Veuf ou veuve", "Veuf", "Veuve")},
    "en": {"celibataire": ("Single",) * 3, "marie": ("Married",) * 3, "pacse": ("Civil partnership",) * 3,
           "divorce": ("Divorced",) * 3, "veuf": ("Widowed",) * 3},
    "es": {"celibataire": ("Soltero/a",) * 3, "marie": ("Casado/a", "Casado", "Casada"), "pacse": ("Pareja de hecho",) * 3,
           "divorce": ("Divorciado/a", "Divorciado", "Divorciada"), "veuf": ("Viudo/a", "Viudo", "Viuda")},
    "de": {"celibataire": ("Ledig",) * 3, "marie": ("Verheiratet",) * 3, "pacse": ("Eingetragene Partnerschaft",) * 3,
           "divorce": ("Geschieden",) * 3, "veuf": ("Verwitwet",) * 3},
    "pt": {"celibataire": ("Solteiro/a",) * 3, "marie": ("Casado/a", "Casado", "Casada"), "pacse": ("União de facto",) * 3,
           "divorce": ("Divorciado/a", "Divorciado", "Divorciada"), "veuf": ("Viúvo/a", "Viúvo", "Viúva")},
    "it": {"celibataire": ("Celibe o nubile",) * 3, "marie": ("Coniugato/a", "Coniugato", "Coniugata"), "pacse": ("Unione civile",) * 3,
           "divorce": ("Divorziato/a", "Divorziato", "Divorziata"), "veuf": ("Vedovo/a", "Vedovo", "Vedova")},
}
_ENFANTS = {"fr": ("1 enfant", "{} enfants"), "en": ("1 child", "{} children"), "es": ("1 hijo", "{} hijos"),
            "de": ("1 Kind", "{} Kinder"), "pt": ("1 filho", "{} filhos"), "it": ("1 figlio", "{} figli")}

# Adjectifs de nationalite, en francais (feminin, accorde avec « nationalite ») et en anglais, pour les pays
# les plus probables. Dans les autres cas, et dans les autres langues : le nom du pays (app/pays/noms.json).
_NATIONALITES = {
    "fr": {"CM": "camerounaise", "CI": "ivoirienne", "SN": "sénégalaise", "GA": "gabonaise", "CG": "congolaise (Congo)", "CD": "congolaise (RDC)",
           "TD": "tchadienne", "CF": "centrafricaine", "GQ": "équato-guinéenne", "BJ": "béninoise", "TG": "togolaise", "BF": "burkinabè",
           "ML": "malienne", "NE": "nigérienne", "NG": "nigériane", "GH": "ghanéenne", "GN": "guinéenne", "GW": "bissau-guinéenne",
           "MR": "mauritanienne", "MA": "marocaine", "DZ": "algérienne", "TN": "tunisienne", "EG": "égyptienne", "MG": "malgache",
           "RW": "rwandaise", "BI": "burundaise", "KM": "comorienne", "DJ": "djiboutienne", "MU": "mauricienne", "HT": "haïtienne",
           "ZA": "sud-africaine", "KE": "kényane", "ET": "éthiopienne", "AO": "angolaise", "FR": "française", "BE": "belge", "CH": "suisse",
           "LU": "luxembourgeoise", "CA": "canadienne", "US": "américaine", "GB": "britannique", "IE": "irlandaise", "DE": "allemande",
           "ES": "espagnole", "IT": "italienne", "PT": "portugaise", "NL": "néerlandaise", "BR": "brésilienne", "CN": "chinoise",
           "IN": "indienne", "LB": "libanaise"},
    "en": {"CM": "Cameroonian", "CI": "Ivorian", "SN": "Senegalese", "GA": "Gabonese", "CG": "Congolese (Congo)", "CD": "Congolese (DRC)",
           "TD": "Chadian", "CF": "Central African", "GQ": "Equatorial Guinean", "BJ": "Beninese", "TG": "Togolese", "BF": "Burkinabe",
           "ML": "Malian", "NE": "Nigerien", "NG": "Nigerian", "GH": "Ghanaian", "GN": "Guinean", "GW": "Bissau-Guinean",
           "MR": "Mauritanian", "MA": "Moroccan", "DZ": "Algerian", "TN": "Tunisian", "EG": "Egyptian", "MG": "Malagasy",
           "RW": "Rwandan", "BI": "Burundian", "KM": "Comorian", "DJ": "Djiboutian", "MU": "Mauritian", "HT": "Haitian",
           "ZA": "South African", "KE": "Kenyan", "ET": "Ethiopian", "AO": "Angolan", "FR": "French", "BE": "Belgian", "CH": "Swiss",
           "LU": "Luxembourgish", "CA": "Canadian", "US": "American", "GB": "British", "IE": "Irish", "DE": "German",
           "ES": "Spanish", "IT": "Italian", "PT": "Portuguese", "NL": "Dutch", "BR": "Brazilian", "CN": "Chinese",
           "IN": "Indian", "LB": "Lebanese"},
}


@lru_cache
def noms_pays() -> dict[str, dict[str, str]]:
    """Noms des pays (code ISO a deux lettres) dans les six langues des documents (source : CLDR)."""
    chemin = Path(__file__).resolve().parent.parent / "pays" / "noms.json"
    return json.loads(chemin.read_text(encoding="utf-8"))


def _langue(code: str | None) -> str:
    courte = (code or "")[:2].lower()
    return courte if courte in LANGUES else "en"


def ecrire_date(d: date, langue: str) -> str:
    """Date en toutes lettres : le mois ecrit evite toute confusion entre jour et mois."""
    mois = _MOIS[langue][d.month - 1]
    if langue == "fr":
        return f"{'1er' if d.day == 1 else d.day} {mois} {d.year}"
    if langue in ("es", "pt"):
        return f"{d.day} de {mois} de {d.year}"
    if langue == "de":
        return f"{d.day}. {mois} {d.year}"
    return f"{d.day} {mois} {d.year}"


def ecrire_nationalite(code: str, langue: str) -> str:
    noms = noms_pays().get(code)
    adjectif = _NATIONALITES.get(langue, {}).get(code)
    return adjectif or (noms[langue] if noms else code)


def ecrire_situation(situation: str | None, enfants: int | None, langue: str) -> str:
    morceaux = []
    if situation in SITUATIONS:
        base, _, accord = situation.partition("_")
        morceaux.append(_SITUATIONS[langue][base][{"": 0, "m": 1, "f": 2}[accord]])
    if enfants:
        un, plusieurs = _ENFANTS[langue]
        morceaux.append(un if enfants == 1 else plusieurs.format(enfants))
    return ", ".join(morceaux)


def renseigne(profil) -> bool:
    """Vrai si le profil contient au moins un element d'etat civil."""
    return any(getattr(profil, c, None) for c in (
        "date_naissance", "lieu_naissance", "nationalite", "situation_familiale", "enfants", "permis_sejour",
    ))


def _montre(f: FichePays | None, champ: str) -> bool:
    return f is None or getattr(f.etat_civil, champ) != "deconseillee"


def lignes(profil, langue: str | None, f: FichePays | None = None) -> list[tuple[str, str]]:
    """Couples (libelle, valeur) a ecrire en tete du CV, filtres selon les usages du pays vise."""
    if profil is None:
        return []
    l = _langue(langue)
    lib = _LIBELLES[l]
    out: list[tuple[str, str]] = []
    if _montre(f, "date_naissance"):
        jour, lieu = profil.date_naissance, profil.lieu_naissance
        if jour and lieu:
            out.append((lib["date_lieu"], f"{ecrire_date(jour, l)}, {lieu}"))
        elif jour:
            out.append((lib["date"], ecrire_date(jour, l)))
        elif lieu:
            out.append((lib["lieu"], lieu))
    if _montre(f, "nationalite"):
        if profil.nationalite:
            out.append((lib["nationalite"], ecrire_nationalite(profil.nationalite, l)))
        if profil.permis_sejour:
            out.append((lib["permis"], profil.permis_sejour))
    if _montre(f, "situation_familiale"):
        situation = ecrire_situation(profil.situation_familiale, profil.enfants, l)
        if situation:
            out.append((lib["situation"], situation))
    return out


def affichage(profil, f: FichePays | None, photo: bool, etat_civil: bool) -> Affichage:
    """Ce que le CV montrera : le choix de la personne, si le profil le permet et si le pays ne le deconseille pas."""
    return Affichage(
        photo=bool(photo and profil.a_photo and (f is None or f.photo != "deconseillee")),
        etat_civil=bool(etat_civil and lignes(profil, "fr", f)),
    )


def photo_en_ligne(profil) -> str | None:
    """Photo du profil, en URI de donnees pour le modele HTML (aucune ressource externe)."""
    octets = profil.photo if profil is not None and profil.a_photo else None
    return f"data:image/jpeg;base64,{b64encode(octets).decode()}" if octets else None
