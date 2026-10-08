import json
import logging
from datetime import datetime

from app.services.llm import IAError, complete as _complete

logger = logging.getLogger(__name__)


def _parse_json(texte: str) -> dict:
    """Extrait un objet JSON d'une reponse, meme entouree de texte ou de balises ```."""
    debut, fin = texte.find("{"), texte.rfind("}")
    if debut == -1 or fin <= debut:
        raise IAError("Aucun JSON dans la reponse du modele")
    try:
        return json.loads(texte[debut:fin + 1])
    except json.JSONDecodeError as e:
        raise IAError(f"JSON invalide: {e}") from e


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

    texte = await _complete(prompt)
    return _parse_json(texte)


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

    texte = await _complete(prompt)
    return _parse_json(texte)


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
        texte = await _complete(prompt)
        data = _parse_json(texte)
        questions = data.get("questions", [])
        if not questions:
            raise ValueError("Aucune question generee")
        return {
            "diagnostic": data.get("diagnostic", "Quelques precisions peuvent renforcer la lettre."),
            "questions": questions[:5],
        }
    except Exception as e:
        logger.warning("Erreur IA questions alignement: %s", e)
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


# --- PHASE 4 : GENERATION DU CV (donnees structurees) ---
def _identite(profil) -> tuple[str, str]:
    nom = getattr(profil, "nom_complet_cv", None)
    email = getattr(profil, "email_cv", None)
    utilisateur = getattr(profil, "utilisateur", None)
    if not nom and utilisateur:
        nom = f"{utilisateur.prenom} {utilisateur.nom}"
    if not email and utilisateur:
        email = utilisateur.email
    return nom or "Candidat", email or ""


async def generer_cv(profil, offre, modele: str = "classique") -> dict:
    """Retourne un dict conforme a CVData ; le rendu est fait par les modeles HTML."""
    nom, email = _identite(profil)
    style = (
        "Format ATS strict : phrases courtes, verbes d'action, chiffres quand ils existent dans le profil."
        if modele == "ats"
        else "Format professionnel soigne, lisible par un recruteur humain comme par un ATS."
    )

    prompt = f"""
    Tu es un expert en recrutement. Construis le CV du candidat, adapte a l'offre visee,
    sous forme d'un objet JSON STRICT (aucun texte avant ou apres, pas de Markdown).

    COORDONNEES:
    - nom: {nom}
    - email: {email or "(non renseigne)"}
    - telephone: {getattr(profil, "telephone", None) or "(non renseigne)"}
    - adresse: {getattr(profil, "adresse", None) or "(non renseignee)"}

    PROFIL DU CANDIDAT (seule source de verite):
    - titre: {profil.titre_profil or "(non renseigne)"}
    - experiences: {_json_dump(profil.experiences)}
    - formations: {_json_dump(profil.formations)}
    - competences: {profil.competences or "(non renseignees)"}
    - langues: {profil.langues or "(non renseignees)"}

    OFFRE VISEE: {offre.titre_poste} chez {offre.entreprise}
    Mots-cles de l'offre: {offre.mots_cles}
    Description:
    {(offre.contenu_brut or "")[:6000]}

    STRUCTURE JSON ATTENDUE:
    {{
      "langue": "code ISO de la langue du CV (fr, en, es...)",
      "labels": {{"resume": "", "experience": "", "formation": "", "competences": "", "langues": ""}},
      "nom": "", "titre": "titre professionnel adapte au poste vise",
      "contact": {{"email": "", "telephone": "", "adresse": ""}},
      "resume": "2 a 3 phrases de profil orientees vers le poste",
      "experiences": [{{"poste": "", "entreprise": "", "lieu": "", "date": "", "puces": ["", ""]}}],
      "formations": [{{"diplome": "", "etablissement": "", "lieu": "", "date": "", "details": ""}}],
      "competences": [{{"categorie": "", "elements": ["", ""]}}],
      "langues": ["Langue (niveau)"]
    }}

    REGLES:
    - Langue: ecris tout le CV dans la langue de l'offre, y compris les titres de section
      ("labels"), par exemple Experience / Education / Skills / Languages en anglais.
    - N'invente RIEN: ni poste, ni entreprise, ni diplome, ni chiffre, ni outil absent du profil.
      Si une information manque, laisse la chaine vide.
    - Recopie a l'identique les postes, entreprises, lieux et dates du profil.
    - Reformule les missions en 3 a 5 puces par experience (jusqu'a 6 pour la plus recente),
      en reprenant naturellement les mots-cles de l'offre quand le profil les justifie.
    - Ordre antichronologique. Regroupe les competences par categorie, les plus pertinentes
      pour l'offre en premier.
    - Aucun crochet, aucun texte entre parentheses de type placeholder.
    - {style}
    """

    texte = await _complete(prompt, max_tokens=8000)
    return _parse_json(texte)


# --- PHASE 4 : GENERATION DE LA LETTRE DE MOTIVATION (donnees structurees) ---
async def generer_lettre_motivation(profil, offre, reponses_alignement=None) -> dict:
    """Retourne un dict conforme a LettreData."""
    nom, email = _identite(profil)
    contact = "\n".join(x for x in (email, getattr(profil, "telephone", None), getattr(profil, "adresse", None)) if x)
    aujourdhui = datetime.now().strftime("%Y-%m-%d")
    contexte_alignement = _json_dump(reponses_alignement or [])

    prompt = f"""
    Redige une lettre de motivation personnelle et profondement alignee avec l'offre.
    Reponds par un objet JSON STRICT (aucun texte avant ou apres, pas de Markdown).

    EXPEDITEUR: {nom}
    COORDONNEES (a recopier): {contact or "(aucune)"}
    DATE DU JOUR (ISO): {aujourdhui}
    DESTINATAIRE: equipe de recrutement de {offre.entreprise}
    POSTE: {offre.titre_poste}

    OFFRE COMPLETE:
    {(offre.contenu_brut or "")[:8000]}

    PROFIL:
    - Titre: {profil.titre_profil}
    - Experiences: {_json_dump(profil.experiences)}
    - Formations: {_json_dump(profil.formations)}
    - Competences: {profil.competences}
    - Langues: {profil.langues}

    REPONSES COMPLEMENTAIRES DU CANDIDAT:
    {contexte_alignement}

    STRUCTURE JSON ATTENDUE:
    {{
      "langue": "code ISO de la langue de la lettre",
      "expediteur_nom": "", "expediteur_contact": "",
      "date": "date du jour ecrite selon les usages de la langue (ex: 8 octobre 2026 / October 8, 2026)",
      "destinataire": "", "objet": "",
      "salutation": "", "paragraphes": ["", ""],
      "formule_finale": "", "signature": ""
    }}

    REGLES:
    - Langue: celle de l'offre, sauf si les reponses du candidat demandent clairement une autre langue.
      Salutation et formule de politesse selon les usages de cette langue et de ce pays.
    - N'invente aucun fait, diplome, chiffre ou publication absent du profil et des reponses.
    - Aucun crochet ni placeholder. Ton professionnel, determine, naturel.
    - 4 a 5 paragraphes courts, 300 a 380 mots au total, en suivant cette logique:
      accroche ciblee (poste, entreprise, raison profonde de l'interet);
      experience principale reliee aux besoins de l'offre;
      autre experience, formation ou realisation pertinente;
      preuves concretes (resultats, outils, responsabilites);
      motivation personnelle et conclusion sobre.
    - Evite les phrases generiques non prouvees par l'offre.
    - signature: {nom}
    """

    texte = await _complete(prompt, max_tokens=6000)
    return _parse_json(texte)
