from groq import Groq
import json
import os
from datetime import datetime
from dotenv import load_dotenv

load_dotenv()
client = Groq(api_key=os.getenv("GROQ_API_KEY"))


def _json_dump(data) -> str:
    return json.dumps(data, ensure_ascii=False, indent=2, default=str)


# --- PHASE 1 : PARSING DU CV ---
async def parser_cv_avec_ia(texte_cv: str) -> dict:
    prompt = f"""
    Analyse ce CV et extrais les informations en JSON STRICT.

    STRUCTURE:
    {{
        "nom_complet_cv": "Nom et prenom trouves sur le document",
        "email_cv": "Email trouve sur le document",
        "telephone": "Telephone",
        "adresse": "Ville, Pays",
        "titre_profil": "Titre professionnel",
        "experiences": [
            {{ "poste": "", "entreprise": "", "lieu": "", "date": "ex: Oct 2023 - Present", "description": [] }}
        ],
        "formations": [
            {{ "diplome": "", "etablissement": "", "lieu": "", "date": "" }}
        ],
        "competences": "skill1, skill2",
        "langues": ""
    }}

    Texte du CV:
    {texte_cv}
    """

    response = client.chat.completions.create(
        model="llama-3.3-70b-versatile",
        messages=[{"role": "user", "content": prompt}],
        response_format={"type": "json_object"},
    )
    return json.loads(response.choices[0].message.content)


extraire_donnees_profil = parser_cv_avec_ia


# --- PHASE 3 : ANALYSE ET MATCHING ---
async def analyser_offre(contenu_offre: str, profil) -> dict:
    profil_data = f"""
    TITRE: {profil.titre_profil or 'Non specifie'}
    COMPETENCES: {profil.competences or 'Non specifiees'}
    EXPERIENCES: {profil.experiences or 'Non renseignees'}
    FORMATIONS: {profil.formations or 'Non renseignees'}
    """

    prompt = f"""
    En tant qu'expert ATS et coach de candidature, analyse l'offre d'emploi par
    rapport au profil du candidat fourni.

    OFFRE:
    {contenu_offre}

    PROFIL DU CANDIDAT:
    {profil_data}

    Tu dois imperativement repondre sous la forme d'un objet JSON valide.
    L'objet JSON doit contenir exactement ces cles:
    - "titre_poste": string, le titre du poste de l'offre
    - "entreprise": string, le nom de l'entreprise
    - "score_compatibilite": int entre 0 et 100
    - "points_forts": list of strings, 3 points forts relies a l'offre
    - "points_manquants": list of strings, 3 points a ameliorer ou a clarifier
    - "mots_cles": list of strings, 8 mots-cles de l'offre
    - "conseil_ia": string, conseil strategique concret pour renforcer la candidature
    """

    try:
        response = client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=[{"role": "user", "content": prompt}],
            response_format={"type": "json_object"},
        )
        return json.loads(response.choices[0].message.content)
    except Exception as e:
        print(f"Erreur IA Matching: {e}")
        return {
            "titre_poste": "Erreur d'analyse",
            "entreprise": "Inconnue",
            "score_compatibilite": 0,
            "points_forts": [],
            "points_manquants": ["Erreur technique avec l'IA"],
            "mots_cles": [],
            "conseil_ia": "Veuillez reessayer l'analyse.",
        }


async def generer_questions_alignement(profil, offre) -> dict:
    profil_data = f"""
    TITRE: {profil.titre_profil or 'Non specifie'}
    COMPETENCES: {profil.competences or 'Non specifiees'}
    EXPERIENCES: {profil.experiences or 'Non renseignees'}
    FORMATIONS: {profil.formations or 'Non renseignees'}
    LANGUES: {profil.langues or 'Non renseignees'}
    """

    prompt = f"""
    Tu es un coach de candidature exigeant. Ton role est d'aider le candidat a
    produire une lettre tres alignee, personnelle et credible, inspiree d'une
    lettre academique qui relie le poste, les projets passes, les preuves
    concretes et la motivation profonde.

    OFFRE:
    Poste: {offre.titre_poste}
    Entreprise: {offre.entreprise}
    Description complete: {offre.contenu_brut}
    Mots-cles: {offre.mots_cles}

    PROFIL CANDIDAT:
    {profil_data}

    Identifie ce qui manque pour ecrire une excellente lettre. Pose uniquement
    des questions dont la reponse peut vraiment ameliorer l'alignement entre
    l'offre et le parcours.

    Reponds en JSON STRICT avec exactement cette structure:
    {{
      "diagnostic": "resume court de l'angle de candidature a renforcer",
      "questions": [
        {{
          "id": "q1",
          "theme": "Experience pertinente",
          "question": "question precise a poser au candidat",
          "aide": "exemple court du type de reponse attendue"
        }}
      ]
    }}

    Contraintes:
    - 3 a 5 questions maximum.
    - Questions concretes, pas generiques.
    - Couvre si utile: motivation secteur/entreprise, preuve d'experience,
      resultat mesurable, projet proche, qualites humaines, conception
      personnelle du metier.
    - Ne demande pas une information deja clairement presente dans le profil.
    """

    try:
        response = client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=[{"role": "user", "content": prompt}],
            response_format={"type": "json_object"},
            temperature=0.35,
        )
        data = json.loads(response.choices[0].message.content)
        questions = data.get("questions", [])
        if not questions:
            raise ValueError("Aucune question generee")
        return {
            "diagnostic": data.get("diagnostic", "Quelques precisions peuvent renforcer la lettre."),
            "questions": questions[:5],
        }
    except Exception as e:
        print(f"Erreur IA Questions Alignement: {e}")
        return {
            "diagnostic": "Quelques precisions aideront a rendre la lettre plus personnelle et convaincante.",
            "questions": [
                {
                    "id": "q1",
                    "theme": "Experience pertinente",
                    "question": "Quelle experience de votre parcours ressemble le plus aux missions de cette offre ?",
                    "aide": "Contexte, probleme traite, actions menees et resultat obtenu.",
                },
                {
                    "id": "q2",
                    "theme": "Motivation",
                    "question": "Qu'est-ce qui vous attire vraiment dans ce poste, cette entreprise ou ce secteur ?",
                    "aide": "Lien avec vos objectifs, vos valeurs ou votre trajectoire professionnelle.",
                },
                {
                    "id": "q3",
                    "theme": "Preuve concrete",
                    "question": "Quel resultat, projet ou apprentissage prouve le mieux votre capacite a reussir dans ce poste ?",
                    "aide": "Resultat mesurable, livrable, publication, responsabilite ou situation marquante.",
                },
            ],
        }


# --- PHASE 4 : GENERATION DE CV PROFESSIONNEL ---
async def generer_cv(profil, offre) -> str:
    nom = getattr(profil, "nom_complet_cv", None)

    if not nom and profil.utilisateur:
        nom = f"{profil.utilisateur.prenom} {profil.utilisateur.nom}"

    email = getattr(profil, "email_cv", None)
    if not email and profil.utilisateur:
        email = profil.utilisateur.email

    tel = getattr(profil, "telephone", "Non renseigne")
    adr = getattr(profil, "adresse", "Non renseignee")

    prompt = f"""
    Tu es un expert en recrutement et en redaction de CV. Redige un CV Markdown professionnel.

    COORDONNEES DU CANDIDAT:
    - NOM: {nom or 'Candidat'}
    - EMAIL: {email or 'Non renseigne'}
    - TEL: {tel}
    - ADRESSE: {adr}

    PARCOURS:
    - EXPERIENCES: {profil.experiences}
    - FORMATIONS: {profil.formations}

    POSTE VISE: {offre.titre_poste} chez {offre.entreprise}

    CONSIGNES:
    1. Utilise "{nom}" en titre.
    2. Pour chaque experience, extrais et affiche: Poste | Entreprise | Lieu | Dates.
    3. Ne jamais utiliser de crochets [ ].
    4. Recupere les lieux et dates exacts presents dans les experiences.
    5. Optimise ATS: reecris les missions avec les mots-cles de l'offre ({offre.mots_cles})
       pour montrer en quoi le parcours prepare au poste de {offre.titre_poste}.
    """

    response = client.chat.completions.create(
        model="llama-3.3-70b-versatile",
        messages=[{"role": "user", "content": prompt}],
        temperature=0.7,
    )
    return response.choices[0].message.content


# --- PHASE 4 : GENERATION DE LETTRE DE MOTIVATION ---
async def generer_lettre_motivation(profil, offre, reponses_alignement=None) -> str:
    nom_expediteur = profil.nom_complet_cv or f"{profil.utilisateur.prenom} {profil.utilisateur.nom}"
    email_expediteur = profil.email_cv or profil.utilisateur.email
    date_du_jour = datetime.now().strftime("%d %B %Y")
    contexte_alignement = _json_dump(reponses_alignement or [])

    prompt = f"""
    Redige une lettre de motivation "Haute Performance", personnelle et profondement alignee.

    EXPEDITEUR: {nom_expediteur} ({email_expediteur})
    DESTINATAIRE: Responsable du recrutement chez {offre.entreprise}
    POSTE: {offre.titre_poste}
    DATE: {date_du_jour}

    OFFRE COMPLETE:
    {offre.contenu_brut}

    PROFIL:
    - Titre: {profil.titre_profil}
    - Experiences: {profil.experiences}
    - Formations: {profil.formations}
    - Competences: {profil.competences}
    - Langues: {profil.langues}

    REPONSES COMPLEMENTAIRES DU CANDIDAT:
    {contexte_alignement}

    REGLES:
    - Interdiction de mettre des crochets [ ].
    - Ton professionnel, determine, naturel, jamais artificiel.
    - Ne pas inventer de faits, de diplomes, de chiffres ou de publications.
    - Construire un lien explicite entre les besoins de l'offre et les experiences du candidat.
    - Suivre cette logique:
      1. Accroche ciblee: poste, entreprise, raison profonde de l'interet.
      2. Experience recente ou principale: contexte, probleme, contribution, lien avec l'offre.
      3. Experience structurante: autre projet, formation, these, stage ou realisation pertinente.
      4. Preuves concretes: resultats, outils, responsabilites, impact.
      5. Motivation personnelle et qualites humaines.
      6. Conclusion sobre avec remerciement.
    - Eviter les phrases generiques comme "votre entreprise leader dans son domaine"
      si elles ne sont pas prouvees par l'offre.
    - Ecrire dans la meme langue que l'offre, sauf si les reponses demandent clairement le francais.
    - Signature finale: {nom_expediteur}.
    """

    response = client.chat.completions.create(
        model="llama-3.3-70b-versatile",
        messages=[{"role": "user", "content": prompt}],
        temperature=0.7,
    )
    return response.choices[0].message.content
