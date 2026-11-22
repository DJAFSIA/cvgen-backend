import json
import logging
from datetime import datetime

from app.pays import AUTRE, consigne_cv, consigne_lettre, liste_pour_detection
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


# --- Langue des textes lus par le candidat (analyse, questions) ---
# Ces textes s'affichent dans l'interface : ils suivent sa langue, pas celle de l'offre.
LANGUES_INTERFACE = {"fr": "francais", "en": "anglais"}


def _consigne_reponse(langue: str, textes: str) -> str:
    nom = LANGUES_INTERFACE.get(langue, "anglais")
    return f"Langue: ecris {textes} en {nom}, la langue de l'interface du candidat, quelle que soit la langue de l'offre ou du profil."


# --- PHASE 3 : ANALYSE ET MATCHING ---
async def analyser_offre(contenu_offre: str, profil, langue: str = "fr") -> dict:
    profil_data = f"""
    TITRE: {profil.titre_profil or 'Non specifie'}
    COMPETENCES: {profil.competences or 'Non specifiees'}
    EXPERIENCES: {profil.experiences or 'Non renseignees'}
    FORMATIONS: {profil.formations or 'Non renseignees'}
    LANGUES: {profil.langues or 'Non renseignees'}
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
    - "pays": string, code du pays ou se trouve le poste, parmi : {liste_pour_detection()} ;
      pour le Canada, "ca-qc" si le poste est au Quebec et "ca" sinon ; "{AUTRE}" si le pays
      n'est pas dans cette liste ou si l'offre ne permet pas de le savoir.

    {_consigne_reponse(langue, '"points_forts", "points_manquants" et "conseil_ia"')}
    Garde "titre_poste", "entreprise" et "mots_cles" tels qu'ils sont ecrits dans l'offre.
    """

    texte = await _complete(prompt)
    return _parse_json(texte)


async def generer_questions_alignement(profil, offre, langue: str = "fr") -> dict:
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
    - {_consigne_reponse(langue, '"diagnostic", "theme", "question" et "aide"')}
    """

    secours = QUESTIONS_SECOURS.get(langue, QUESTIONS_SECOURS["en"])
    try:
        texte = await _complete(prompt)
        data = _parse_json(texte)
        questions = data.get("questions", [])
        if not questions:
            raise ValueError("Aucune question generee")
        return {
            "diagnostic": data.get("diagnostic", secours["diagnostic_court"]),
            "questions": questions[:5],
        }
    except Exception as e:
        logger.warning("Erreur IA questions alignement: %s", e)
        return {"diagnostic": secours["diagnostic"], "questions": secours["questions"]}


# Questions de secours si l'IA ne repond pas, dans la langue de l'interface
QUESTIONS_SECOURS = {
    "fr": {
        "diagnostic_court": "Quelques precisions peuvent renforcer la lettre.",
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
    },
    "en": {
        "diagnostic_court": "A few details can make the letter stronger.",
        "diagnostic": "A few details will make the letter more personal and convincing.",
        "questions": [
            {
                "id": "q1",
                "theme": "Relevant experience",
                "question": "Which experience in your background is closest to the duties in this job offer?",
                "aide": "Context, the problem you handled, what you did and the result.",
            },
            {
                "id": "q2",
                "theme": "Motivation",
                "question": "What really draws you to this role, this company or this sector?",
                "aide": "How it connects to your goals, your values or your career path.",
            },
            {
                "id": "q3",
                "theme": "Concrete proof",
                "question": "Which result, project or lesson best shows that you can succeed in this role?",
                "aide": "A measurable result, a deliverable, a publication, a responsibility or a key situation.",
            },
        ],
    },
}


# --- Langue des documents ---
LANGUES_DOCUMENTS = {
    "fr": "francais", "en": "anglais", "es": "espagnol", "de": "allemand", "pt": "portugais", "it": "italien",
}


def _consigne_langue(langue: str, document: str) -> str:
    if langue in LANGUES_DOCUMENTS:
        return (
            f"Langue: ecris {document} en {LANGUES_DOCUMENTS[langue]} (code \"{langue}\"), quelle que soit la "
            f"langue de l'offre ou du profil, y compris les titres de section (\"labels\"). Traduis les "
            f"descriptions de missions si besoin, mais ne traduis pas les noms propres (entreprises, "
            f"etablissements, outils, logiciels) ni les dates."
        )
    return (
        f"Langue: ecris {document} dans la langue de l'offre, y compris les titres de section "
        f"(\"labels\"), par exemple Experience / Education / Skills / Languages en anglais. "
        f"Si les reponses du candidat demandent clairement une autre langue, utilise celle-ci."
    )


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


async def generer_cv(profil, offre, modele: str = "classique", langue: str = "auto", fiche_pays=None) -> dict:
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
      "nom": "", "titre": "titre professionnel du candidat, tel que dans son profil",
      "contact": {{"email": "", "telephone": "", "adresse": ""}},
      "resume": "2 a 3 phrases de profil orientees vers le poste",
      "experiences": [{{"poste": "", "entreprise": "", "lieu": "", "date": "", "puces": ["", ""]}}],
      "formations": [{{"diplome": "", "etablissement": "", "lieu": "", "date": "", "details": ""}}],
      "competences": [{{"categorie": "", "elements": ["", ""]}}],
      "langues": ["Langue (niveau)"]
    }}

    REGLES:
    - {_consigne_langue(langue, "le CV")}
    - N'invente RIEN: ni poste, ni entreprise, ni diplome, ni chiffre, ni outil absent du profil.
      Si une information manque, laisse la chaine vide.
    - Recopie a l'identique les postes, entreprises, lieux et dates du profil.
    - Le titre du CV reprend celui du profil : ne l'eleve jamais en niveau (pas de "Senior", "Lead",
      "Manager" s'il n'y figure pas), et ne le remplace pas par l'intitule de l'offre.
    - N'attribue un outil, une technologie ou un resultat a un poste precis que si la description de
      ce poste dans le profil le dit. Les competences listees sans contexte vont uniquement dans la
      section competences.
    - Ne gonfle pas les niveaux (pas de "expert", "avance") sans source dans le profil.
    - Reformule les missions en 3 a 5 puces par experience (jusqu'a 6 pour la plus recente),
      en reprenant naturellement les mots-cles de l'offre quand le profil les justifie.
    - Ordre antichronologique. Regroupe les competences par categorie, les plus pertinentes
      pour l'offre en premier.
    - Aucun crochet, aucun texte entre parentheses de type placeholder.
    - {style}
    {consigne_cv(fiche_pays)}
    """

    texte = await _complete(prompt, max_tokens=8000)
    return _parse_json(texte)


# --- PHASE 4 : GENERATION DE LA LETTRE DE MOTIVATION (donnees structurees) ---
async def generer_lettre_motivation(profil, offre, reponses_alignement=None, langue: str = "auto", fiche_pays=None) -> dict:
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
    - {_consigne_langue(langue, "la lettre")}
      Salutation et formule de politesse selon les usages de cette langue et de ce pays.
    - N'invente aucun fait, diplome, chiffre ou publication absent du profil et des reponses.
    - N'affirme jamais une connaissance prealable de l'entreprise ("j'ai suivi vos travaux", "votre
      plateforme", etc.) sauf si l'offre ou les reponses du candidat le permettent. N'exagere pas
      les niveaux ("expert", "avance") sans source.
    - Aucun crochet ni placeholder. Ton professionnel, determine, naturel.
    - 4 a 5 paragraphes courts, 300 a 380 mots au total, en suivant cette logique:
      accroche ciblee (poste, entreprise, raison profonde de l'interet);
      experience principale reliee aux besoins de l'offre;
      autre experience, formation ou realisation pertinente;
      preuves concretes (resultats, outils, responsabilites);
      motivation personnelle et conclusion sobre.
    - Evite les phrases generiques non prouvees par l'offre.
    - signature: {nom}
    {consigne_lettre(fiche_pays)}
    """

    texte = await _complete(prompt, max_tokens=6000)
    return _parse_json(texte)
