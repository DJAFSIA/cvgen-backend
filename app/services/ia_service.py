from groq import Groq
import json
import os
from datetime import datetime
from dotenv import load_dotenv

load_dotenv()
client = Groq(api_key=os.getenv("GROQ_API_KEY"))

# --- PHASE 1 : PARSING DU CV ---
async def parser_cv_avec_ia(texte_cv: str) -> dict:
    prompt = f"""
    Analyse ce CV et extrais les infos en JSON STRICT.
    STRUCTURE :
    {{
        "nom_complet_cv": "Nom et Prénom trouvés sur le document",
        "email_cv": "Email trouvé sur le document",
        "telephone": "Téléphone",
        "adresse": "Ville, Pays",
        "titre_profil": "Titre pro",
        "experiences": [
            {{ "poste": "", "entreprise": "", "lieu": "", "date": "ex: Oct 2023 - Présent", "description": [] }}
        ],
        "formations": [
            {{ "diplome": "", "etablissement": "", "lieu": "", "date": "" }}
        ],
        "competences": "skill1, skill2",
        "langues": ""
    }}
    Texte du CV : {texte_cv}
    """

    response = client.chat.completions.create(
        model="llama-3.3-70b-versatile",
        messages=[{"role": "user", "content": prompt}],
        response_format={ "type": "json_object" }
    )
    return json.loads(response.choices[0].message.content)

extraire_donnees_profil = parser_cv_avec_ia

# --- PHASE 3 : ANALYSE ET MATCHING ---
async def analyser_offre(contenu_offre: str, profil) -> dict:
    # Correction : On définit profil_data avant de l'utiliser
    profil_data = f"""
    TITRE: {profil.titre_profil or 'Non spécifié'}
    COMPÉTENCES: {profil.competences or 'Non spécifiées'}
    EXPÉRIENCES: {profil.experiences or 'Non renseignées'}
    """
    
    prompt = f"""En tant qu'expert ATS, analyse l'offre d'emploi par rapport au profil du candidat fourni.
    
    OFFRE: {contenu_offre}
    
    PROFIL DU CANDIDAT: 
    {profil_data}

    Tu dois impérativement répondre sous la forme d'un objet **json** valide.
    L'objet **json** doit contenir exactement ces clés : 
    - "titre_poste": (string) le titre du poste de l'offre
    - "entreprise": (string) le nom de l'entreprise
    - "score_compatibilite": (int entre 0 et 100)
    - "points_forts": (list of strings) 3 points forts
    - "points_manquants": (list of strings) 3 points à améliorer
    - "mots_cles": (list of strings) 8 mots-clés de l'offre
    - "conseil_ia": (string) un conseil stratégique
    """

    try:
        response = client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=[{"role": "user", "content": prompt}],
            response_format={ "type": "json_object" }
        )
        return json.loads(response.choices[0].message.content)
    except Exception as e:
        print(f"Erreur IA Matching: {e}")
        # Retour de secours pour éviter le crash du front
        return {
            "titre_poste": "Erreur d'analyse",
            "entreprise": "Inconnue",
            "score_compatibilite": 0,
            "points_forts": [],
            "points_manquants": ["Erreur technique avec l'IA"],
            "mots_cles": [],
            "conseil_ia": "Veuillez réessayer l'analyse."
        }

# --- PHASE 4 : GÉNÉRATION DE CV PROFESSIONNEL ---
async def generer_cv(profil, offre) -> str:
    nom = getattr(profil, 'nom_complet_cv', None)
    
    # Si nom_complet_cv est vide ou n'existe pas, on prend le nom du compte login
    if not nom and profil.utilisateur:
        nom = f"{profil.utilisateur.prenom} {profil.utilisateur.nom}"
    
    email = getattr(profil, 'email_cv', None)
    if not email and profil.utilisateur:
        email = profil.utilisateur.email

    tel = getattr(profil, 'telephone', 'Non renseigné')
    adr = getattr(profil, 'adresse', 'Non renseignée')

    prompt = f"""
    Tu es un expert en recrutement et en rédaction de CV. Rédige un CV Markdown professionnel.
    
    COORDONNÉES DU CANDIDAT :
     - NOM : {nom or 'Candidat'}
    - EMAIL : {email or 'Non renseigné'}
    - TEL : {tel}
    - ADRESSE : {adr}
    PARCOURS (Données structurées) :
    - EXPÉRIENCES : {profil.experiences}
    - FORMATIONS : {profil.formations}
    
    POSTE VISÉ : {offre.titre_poste} chez {offre.entreprise}

    CONSIGNES :
    1. Utilise "{nom}" en titre.
    2. Pour CHAQUE expérience dans la liste, tu DOIS extraire et afficher : 
       **Poste | Entreprise | Lieu | Dates**.
    3. NE JAMAIS utiliser de crochets [ ].
    4. Récupère les lieux et dates exacts présents dans le JSON des expériences.
    5. OPTIMISATION ATS : Pour chaque expérience, ne te contente pas de lister les tâches. 
   Réécris-les en utilisant les mots-clés de l'offre ({offre.mots_cles}) pour montrer 
   en quoi cette expérience passée prépare parfaitement au poste de {offre.titre_poste}.
    """
    response = client.chat.completions.create(
        model="llama-3.3-70b-versatile",
        messages=[{"role": "user", "content": prompt}],
        temperature=0.7
    )
    return response.choices[0].message.content

# --- PHASE 4 : GÉNÉRATION DE LETTRE DE MOTIVATION ---
async def generer_lettre_motivation(profil, offre) -> str:
    nom_expediteur = profil.nom_complet_cv or f"{profil.utilisateur.prenom} {profil.utilisateur.nom}"
    email_expediteur = profil.email_cv or profil.utilisateur.email
    date_du_jour = datetime.now().strftime("%d %B %Y")

    prompt = f"""Rédige une lettre de motivation "Haute Performance".
    EXPÉDITEUR : {nom_expediteur} ({email_expediteur})
    DESTINATAIRE : Responsable du recrutement chez {offre.entreprise}
    POSTE : {offre.titre_poste}
    DATE : {date_du_jour}

    CONTENU :
    Utilise les expériences suivantes pour convaincre : {profil.experiences}
    
    RÈGLES :
    - INTERDICTION de mettre des crochets [ ].
    - Ton : Professionnel et déterminé.
    - Signature finale : {nom_expediteur}.
    """

    response = client.chat.completions.create(
        model="llama-3.3-70b-versatile",
        messages=[{"role": "user", "content": prompt}],
        temperature=0.7
    )
    return response.choices[0].message.content