from typing import Annotated, Any, List, Literal

from pydantic import BaseModel, BeforeValidator, ConfigDict, Field, field_validator

ModeleCV = Literal["classique", "moderne", "ats"]
MODELES_CV = ("classique", "moderne", "ats")


def _texte(v: Any) -> str:
    if v is None:
        return ""
    if isinstance(v, (list, tuple)):
        return ", ".join(_texte(x) for x in v if x is not None)
    if isinstance(v, dict):
        return ", ".join(f"{k}: {_texte(x)}" for k, x in v.items() if x is not None)
    return str(v).strip()


def _liste_texte(v: Any) -> list:
    if v is None or v == "":
        return []
    if not isinstance(v, (list, tuple)):
        v = [v]
    return [t for t in (_texte(x) for x in v) if t]


# Types tolerants aux sorties imparfaites du LLM (null, nombres, listes a la place de texte)
Texte = Annotated[str, BeforeValidator(_texte)]
ListeTexte = Annotated[List[str], BeforeValidator(_liste_texte)]


class _Tolerant(BaseModel):
    """Les sorties du LLM sont normalisees : champs manquants ou null vides, extras ignores."""

    model_config = ConfigDict(extra="ignore")

    @field_validator("*", mode="before")
    @classmethod
    def _none_en_defaut(cls, v, info):
        if v is None:
            field = cls.model_fields[info.field_name]
            return field.get_default(call_default_factory=True)
        return v


class Labels(_Tolerant):
    resume: Texte = "Profil"
    experience: Texte = "Experience professionnelle"
    formation: Texte = "Formation"
    competences: Texte = "Competences"
    langues: Texte = "Langues"


class Contact(_Tolerant):
    email: Texte = ""
    telephone: Texte = ""
    adresse: Texte = ""


class ExperienceCV(_Tolerant):
    poste: Texte = ""
    entreprise: Texte = ""
    lieu: Texte = ""
    date: Texte = ""
    puces: ListeTexte = Field(default_factory=list)


class FormationCV(_Tolerant):
    diplome: Texte = ""
    etablissement: Texte = ""
    lieu: Texte = ""
    date: Texte = ""
    details: Texte = ""


class GroupeCompetences(_Tolerant):
    categorie: Texte = ""
    elements: ListeTexte = Field(default_factory=list)


class CVData(_Tolerant):
    langue: Texte = "fr"
    labels: Labels = Field(default_factory=Labels)
    nom: Texte = ""
    titre: Texte = ""
    contact: Contact = Field(default_factory=Contact)
    resume: Texte = ""
    experiences: List[ExperienceCV] = Field(default_factory=list)
    formations: List[FormationCV] = Field(default_factory=list)
    competences: List[GroupeCompetences] = Field(default_factory=list)
    langues: ListeTexte = Field(default_factory=list)


class LettreData(_Tolerant):
    langue: Texte = "fr"
    expediteur_nom: Texte = ""
    expediteur_contact: Texte = ""
    date: Texte = ""
    destinataire: Texte = ""
    objet: Texte = ""
    salutation: Texte = ""
    paragraphes: ListeTexte = Field(default_factory=list)
    formule_finale: Texte = ""
    signature: Texte = ""
