"""Ce que l'IA recoit : l'analyse d'une offre doit voir tout le profil, langues comprises."""
import asyncio
from types import SimpleNamespace

from app.services import ia_service


def test_l_analyse_d_une_offre_voit_les_langues_du_profil(monkeypatch):
    recu = {}

    async def fausse_reponse(prompt, *args, **kwargs):
        recu["prompt"] = prompt
        return '{"score_compatibilite": 80}'

    monkeypatch.setattr(ia_service, "_complete", fausse_reponse)
    profil = SimpleNamespace(titre_profil="Cheffe de projet", competences="Jira", experiences=[], formations=[], langues="Anglais courant")
    assert asyncio.run(ia_service.analyser_offre("Offre exigeant un anglais professionnel", profil))["score_compatibilite"] == 80
    assert "Anglais courant" in recu["prompt"]


# --- Langue des textes lus par le candidat : celle de l'interface, pas celle de l'offre ---

def _profil():
    return SimpleNamespace(titre_profil="Cheffe de projet", competences="Jira", experiences=[], formations=[], langues="Anglais")


def test_l_analyse_est_redigee_dans_la_langue_de_l_interface(monkeypatch):
    prompts = []

    async def fausse_reponse(prompt, *args, **kwargs):
        prompts.append(prompt)
        return '{"score_compatibilite": 70}'

    monkeypatch.setattr(ia_service, "_complete", fausse_reponse)
    asyncio.run(ia_service.analyser_offre("Digital project manager wanted in Douala", _profil(), "en"))
    asyncio.run(ia_service.analyser_offre("Digital project manager wanted in Douala", _profil(), "fr"))
    assert "en anglais, la langue de l'interface" in prompts[0]
    assert "en francais, la langue de l'interface" in prompts[1]
    # les mots cles restent ceux de l'offre (ils servent a la correspondance avec le CV)
    assert "tels qu'ils sont ecrits dans l'offre" in prompts[0]


def test_les_questions_de_secours_suivent_la_langue_de_l_interface(monkeypatch):
    async def panne(*args, **kwargs):
        raise ia_service.IAError("panne simulee")

    monkeypatch.setattr(ia_service, "_complete", panne)
    offre = SimpleNamespace(titre_poste="PM", entreprise="Exemple", contenu_brut="x", mots_cles="Jira")
    en = asyncio.run(ia_service.generer_questions_alignement(_profil(), offre, "en"))
    fr = asyncio.run(ia_service.generer_questions_alignement(_profil(), offre, "fr"))
    assert en["questions"][0]["question"].startswith("Which experience")
    assert fr["questions"][0]["question"].startswith("Quelle experience")


def test_la_route_d_analyse_transmet_la_langue_du_site_sinon_celle_du_compte(client, make_user, monkeypatch):
    import app.routers.offre as routes

    recues = []

    async def fausse_analyse(contenu, profil, langue):
        recues.append(langue)
        return {"titre_poste": "PM", "entreprise": "Exemple", "score_compatibilite": 75, "mots_cles": ["Jira"]}

    monkeypatch.setattr(routes, "analyser_offre", fausse_analyse)
    _, h = make_user(langue="fr")
    offre = {"contenu_brut": "Digital project manager wanted in Douala, Jira and agile methods."}
    r = client.post("/offre/", json={**offre, "langue": "en"}, headers=h)
    assert r.status_code == 200, r.text
    r = client.post("/offre/", json=offre, headers=h)
    assert r.status_code == 200, r.text
    assert recues == ["en", "fr"]
    # champ absent de la reponse de l'IA : texte de repli dans la langue de l'interface
    assert r.json()["conseil_ia"] == "Pas de conseil disponible"
