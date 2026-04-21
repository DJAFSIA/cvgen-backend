from groq import Groq
import json
import os
from dotenv import load_dotenv

load_dotenv()
client = Groq(api_key=os.getenv("GROQ_API_KEY"))

# --- PHASE 1 : PARSING DU CV ---
async def parser_cv_avec_ia(texte_cv: str) -> dict:
    prompt = f"""Tu es un expert en recrutement. Analyse ce texte de CV et extrait les informations au format JSON.
    Structure attendue :
    {{
        "nom": "nom", "prenom": "prénom", "titre_profil": "poste",
        "competences": "skills", "experiences": "résumé XP",
        "formations": "études", "langues": "langues"
    }}
    Texte : {texte_cv}"""

    response = client.chat.completions.create(
        model="llama-3.3-70b-versatile",
        messages=[{"role": "user", "content": prompt}],
        response_format={ "type": "json_object" }
    )
    return json.loads(response.choices[0].message.content)

extraire_donnees_profil = parser_cv_avec_ia

# --- PHASE 3 : ANALYSE ET MATCHING ---
async def analyser_offre(contenu_offre: str, profil) -> dict:
    # On prépare un résumé du profil pour l'IA
    profil_data = f"""
    TITRE: {profil.titre_profil}
    COMPÉTENCES: {profil.competences}
    EXPÉRIENCES: {profil.experiences}
    """

    prompt = f"""
    En tant qu'expert en recrutement, analyse cette offre d'emploi par rapport au profil du candidat.
    
    PROFIL CANDIDAT:
    {profil_data}

    OFFRE D'EMPLOI:
    {contenu_offre}

    Tu DOIS impérativement retourner un JSON avec TOUS les champs suivants remplis (ne laisse rien de vide) :
    {{
        "titre_poste": "Le titre du poste trouvé dans l'offre",
        "entreprise": "Le nom de l'entreprise trouvé",
        "score_compatibilite": (un entier entre 0 et 100),
        "points_forts": ["Donne au moins 3 points forts ou correspondances même minimes"],
        "points_manquants": ["Donne au moins 3 compétences ou mots-clés qui manquent au candidat"],
        "mots_cles": ["8 mots-clés techniques de l'offre"],
        "conseil_ia": "Donne un conseil concret pour que le candidat améliore ce score"
    }}
    CONSIGNES STRICTES :
    - "points_forts" : Même si le score est bas, trouve au moins 2 points communs (ex: langue, soft skills, diplôme).
    - "points_manquants" : Liste les 3 compétences techniques les plus importantes de l'offre que le candidat n'a pas.
    - "conseil_ia" : Sois encourageant et donne une action concrète.
    
    RETOURNE UN JSON COMPLET. NE JAMAIS RENVOYER DE LISTE VIDE.
    """

    response = client.chat.completions.create(
        model="llama-3.3-70b-versatile",
        messages=[{"role": "user", "content": prompt}],
        response_format={ "type": "json_object" }
    )
    
    return json.loads(response.choices[0].message.content)

# --- PHASE 4 : GÉNÉRATION ---
async def generer_cv(profil, offre) -> str:
    prompt = f"Rédige un CV pour {offre.titre_poste} basé sur {profil.experiences}"
    response = client.chat.completions.create(model="llama-3.3-70b-versatile", messages=[{"role": "user", "content": prompt}])
    return response.choices[0].message.content

async def generer_lettre_motivation(profil, offre) -> str:
    prompt = f"Rédige une lettre pour {offre.titre_poste}"
    response = client.chat.completions.create(model="llama-3.3-70b-versatile", messages=[{"role": "user", "content": prompt}])
    return response.choices[0].message.content