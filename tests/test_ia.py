"""Ce que l'IA recoit : l'analyse d'une offre doit voir tout le profil, langues comprises."""
import asyncio
import time
from types import SimpleNamespace

import httpx
import pytest

from app.core.config import settings
from app.services import ia_service, llm


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
    assert fr["questions"][0]["question"].startswith("Quelle expérience")


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


# --- Chaine de modeles et de fournisseurs : un modele sature ou muet laisse sa place ---

@pytest.fixture
def gemini(monkeypatch):
    """Gemini simule : `reponses` donne, pour chaque modele, la suite de ses reponses (code HTTP ou exception)."""
    appels, reponses = [], {}

    def repondre(requete):
        modele = requete.url.path.split("/models/")[1].split(":")[0]
        appels.append(modele)
        suite = reponses[modele]
        resultat = suite.pop(0) if len(suite) > 1 else suite[0]
        if isinstance(resultat, Exception):
            raise resultat
        if resultat == 200:
            return httpx.Response(200, json={"candidates": [{"content": {"parts": [{"text": f"reponse de {modele}"}]}}]})
        return httpx.Response(resultat, text="erreur simulee")

    async def sans_attente(_):
        return None

    vrai_client = httpx.AsyncClient
    monkeypatch.setattr(llm.httpx, "AsyncClient", lambda **kw: vrai_client(transport=httpx.MockTransport(repondre), **kw))
    monkeypatch.setattr(llm.asyncio, "sleep", sans_attente)
    monkeypatch.setattr(settings, "LLM_PROVIDERS", "gemini")
    monkeypatch.setattr(settings, "GEMINI_API_KEY", "cle-de-test")
    monkeypatch.setattr(settings, "GEMINI_MODEL", "a")
    monkeypatch.setattr(settings, "GEMINI_FALLBACK_MODELS", "b,c")
    return SimpleNamespace(appels=appels, reponses=reponses)


@pytest.mark.parametrize("panne", [503, 429, 404, httpx.ReadTimeout("muet"), httpx.ConnectError("coupe")], ids=["sature", "quota", "retire", "muet", "coupe"])
def test_un_modele_en_panne_laisse_tout_de_suite_sa_place(gemini, panne):
    gemini.reponses.update({"a": [panne], "b": [200], "c": [200]})
    assert asyncio.run(llm.complete("x")) == "reponse de b"
    assert gemini.appels == ["a", "b"]


def test_un_second_passage_a_lieu_si_tous_les_modeles_sont_satures(gemini):
    gemini.reponses.update({"a": [503, 200], "b": [503], "c": [503]})
    assert asyncio.run(llm.complete("x")) == "reponse de a"
    assert gemini.appels == ["a", "b", "c", "a"]


def test_une_requete_refusee_n_est_pas_renvoyee(gemini):
    gemini.reponses.update({"a": [400], "b": [200], "c": [200]})
    with pytest.raises(llm.IAError):
        asyncio.run(llm.complete("x"))
    assert gemini.appels == ["a"]


def test_l_attente_totale_est_bornee(monkeypatch):
    async def muet(*args):
        await asyncio.Event().wait()

    monkeypatch.setattr(llm, "_un_fournisseur", muet)
    monkeypatch.setattr(llm, "_est_configure", lambda p: True)
    monkeypatch.setattr(settings, "LLM_PROVIDERS", "gemini")
    debut = time.monotonic()
    with pytest.raises(llm.IAError):
        asyncio.run(llm.complete("x", essai=0.05, delai=0.2))
    assert time.monotonic() - debut < 3


def test_un_fournisseur_muet_laisse_du_temps_au_suivant(monkeypatch):
    async def fournisseur(provider, *args):
        if provider == "gemini":
            await asyncio.Event().wait()
        return "reponse de groq"

    monkeypatch.setattr(llm, "_un_fournisseur", fournisseur)
    monkeypatch.setattr(llm, "_est_configure", lambda p: True)
    monkeypatch.setattr(settings, "LLM_PROVIDERS", "gemini,groq")
    assert asyncio.run(llm.complete("x", essai=0.05, delai=0.4)) == "reponse de groq"


def test_les_questions_n_attendent_pas_aussi_longtemps_que_la_generation(monkeypatch):
    recu = {}

    async def fausse_reponse(prompt, **kwargs):
        recu.update(kwargs)
        return '{"diagnostic": "d", "questions": [{"id": "q1", "theme": "t", "question": "q", "aide": "a"}]}'

    monkeypatch.setattr(ia_service, "_complete", fausse_reponse)
    offre = SimpleNamespace(titre_poste="PM", entreprise="Exemple", contenu_brut="x", mots_cles="Jira")
    asyncio.run(ia_service.generer_questions_alignement(_profil(), offre, "fr"))
    assert recu["delai"] < llm.DELAI_TOTAL and recu["essai"] < llm.DELAI_ESSAI
