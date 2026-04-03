from groq import Groq
import json
import os
from dotenv import load_dotenv

load_dotenv()
client = Groq(api_key=os.getenv("GROQ_API_KEY"))

async def analyser_offre(contenu_offre: str, profil) -> dict:
    prompt = f"""Analyse cette offre d'emploi et retourne un JSON avec :
- titre_poste (string)
- entreprise (string)
- mots_cles (liste de strings, max 10)
- score_compatibilite (float entre 0 et 100)

Profil du candidat :
Titre : {profil.titre_profil or 'Non renseigné'}
Compétences : {profil.competences or 'Non renseignées'}
Expériences : {profil.experiences or 'Non renseignées'}

Offre d'emploi :
{contenu_offre}

Réponds UNIQUEMENT avec le JSON, sans texte autour."""

    response = client.chat.completions.create(
        model="llama-3.3-70b-versatile",
        messages=[{"role": "user", "content": prompt}],
        max_tokens=1000,
    )

    texte = response.choices[0].message.content.strip()
    texte = texte.replace("```json", "").replace("```", "").strip()

    try:
        return json.loads(texte)
    except Exception:
        return {
            "titre_poste": None,
            "entreprise": None,
            "mots_cles": [],
            "score_compatibilite": None,
        }


async def generer_cv(profil, offre, modele: str = "classique") -> str:
    prompt = f"""Tu es un expert en rédaction de CV professionnels.
Génère un CV complet et professionnel. Utilise UNIQUEMENT les informations fournies.

PROFIL :
Titre : {profil.titre_profil or 'Non renseigné'}
Expériences : {profil.experiences or 'Non renseignées'}
Formations : {profil.formations or 'Non renseignées'}
Compétences : {profil.competences or 'Non renseignées'}
Langues : {profil.langues or 'Non renseignées'}

OFFRE CIBLÉE :
Poste : {offre.titre_poste or 'Non spécifié'}
Entreprise : {offre.entreprise or 'Non spécifiée'}
Mots-clés : {offre.mots_cles or 'Non extraits'}

Génère le CV maintenant."""

    response = client.chat.completions.create(
        model="llama-3.3-70b-versatile",
        messages=[{"role": "user", "content": prompt}],
        max_tokens=2000,
    )
    return response.choices[0].message.content


async def generer_lettre_motivation(profil, offre, ton: str = "professionnel") -> str:
    prompt = f"""Tu es un expert en lettres de motivation.
Génère une lettre professionnelle et personnalisée. Ton : {ton}.
Utilise UNIQUEMENT les informations fournies.

PROFIL :
Titre : {profil.titre_profil or 'Non renseigné'}
Expériences : {profil.experiences or 'Non renseignées'}
Compétences : {profil.competences or 'Non renseignées'}

OFFRE :
Poste : {offre.titre_poste or 'Non spécifié'}
Entreprise : {offre.entreprise or 'Non spécifiée'}

Génère la lettre maintenant."""

    response = client.chat.completions.create(
        model="llama-3.3-70b-versatile",
        messages=[{"role": "user", "content": prompt}],
        max_tokens=2000,
    )
    return response.choices[0].message.content