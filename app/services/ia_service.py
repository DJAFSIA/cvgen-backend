from groq import Groq
import json
import os
from datetime import datetime
from dotenv import load_dotenv

load_dotenv()
client = Groq(api_key=os.getenv("GROQ_API_KEY"))

# --- PHASE 1 : PARSING DU CV ---
async def parser_cv_avec_ia(texte_cv: str) -> dict:
    prompt = f"""Tu es un expert en recrutement. Analyse ce texte de CV et extrait les informations au format JSON.
    Structure attendue :
    {{
        "nom": "nom", "prenom": "prénom", "titre_profil": "poste actuel",
        "competences": "skills", "experiences": "résumé détaillé XP",
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
    profil_data = f"TITRE: {profil.titre_profil}\nSKILLS: {profil.competences}\nXP: {profil.experiences}"
    
    prompt = f"""En tant qu'expert ATS (Applicant Tracking System), analyse l'offre par rapport au profil.
    OFFRE: {contenu_offre}
    PROFIL: {profil_data}

    Retourne un JSON avec :
    - titre_poste, entreprise, score_compatibilite (int)
    - points_forts (list), points_manquants (list), conseil_ia (string)
    FORCE l'IA à remplir tous les champs. Ne renvoie jamais de listes vides."""

    response = client.chat.completions.create(
        model="llama-3.3-70b-versatile",
        messages=[{"role": "user", "content": prompt}],
        response_format={ "type": "json_object" }
    )
    return json.loads(response.choices[0].message.content)

# --- PHASE 4 : GÉNÉRATION DE CV PROFESSIONNEL ---
async def generer_cv(profil, offre) -> str:
    # On prépare les données du profil (extraites en Phase 1)
    # On n'utilise PAS profil.utilisateur ici si on veut rester fidèle au CV importé
    
    prompt = f"""
    Tu es un expert en recrutement. Rédige un CV professionnel complet.
    
    SOURCE DES DONNÉES (À utiliser exclusivement) :
    - Identité et Titre : {profil.titre_profil}
    - Expériences professionnelles : {profil.experiences}
    - Formations et diplômes : {profil.formations}
    - Compétences techniques : {profil.competences}
    - Langues : {profil.langues}
    
    POSTE CIBLÉ POUR L'ADAPTATION :
    {offre.titre_poste} chez {offre.entreprise} (Mots-clés : {offre.mots_cles})

    CONSIGNES STRICTES :
    1. NE JAMAIS utiliser de texte entre crochets comme [Nom] ou [Date]. 
    2. Utilise les informations de l'identité présentes dans : {profil.titre_profil}.
    3. Reformule les expériences pour qu'elles valorisent le candidat par rapport au poste de {offre.titre_poste}.
    4. Structure : En-tête, Résumé, Expériences, Formations, Compétences.
    5. Formate en Markdown propre.
    """

    response = client.chat.completions.create(
        model="llama-3.3-70b-versatile",
        messages=[{"role": "user", "content": prompt}],
        temperature=0.7 # Un peu de créativité pour la reformulation
    )
    return response.choices[0].message.content

# --- PHASE 4 : GÉNÉRATION DE LETTRE DE MOTIVATION ---
async def generer_lettre_motivation(profil, offre) -> str:
    identite = f"{profil.utilisateur.prenom} {profil.utilisateur.nom}"
    date_du_jour = datetime.now().strftime("%d %B %Y")

    prompt = f"""Rédige une lettre de motivation d'expert pour {identite}.
    
    CIBLE : Poste de {offre.titre_poste} chez {offre.entreprise}.
    PROFIL DU CANDIDAT : {profil.experiences} et {profil.competences}.
    DATE : {date_du_jour}

    RÈGLES D'OR :
    1. AUCUN TEXTE ENTRE CROCHETS. Si une info manque (ex: nom du recruteur), écris "À l'attention du Responsable du Recrutement".
    2. Utilise le nom "{identite}" pour la signature.
    3. Structure : 
       - MOI : Accroche percutante montrant la compréhension des besoins de {offre.entreprise}.
       - VOUS : Pourquoi leurs projets m'intéressent.
       - NOUS : La valeur ajoutée concrète que j'apporte.
    4. Ton : Professionnel, déterminé et humain. Évite les phrases trop clichés.
    """

    response = client.chat.completions.create(
        model="llama-3.3-70b-versatile",
        messages=[{"role": "user", "content": prompt}],
        temperature=0.7
    )
    return response.choices[0].message.content