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
