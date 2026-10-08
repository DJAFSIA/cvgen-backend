from pathlib import Path

from markupsafe import Markup
from jinja2 import Environment, FileSystemLoader, select_autoescape
from markdown_it import MarkdownIt

from app.schemas.document import CVData, LettreData, MODELES_CV

TEMPLATES_DIR = Path(__file__).resolve().parent.parent / "templates"

_env = Environment(
    loader=FileSystemLoader(TEMPLATES_DIR),
    autoescape=select_autoescape(["html"]),
)
# CSS statique du depot (jamais issu d'une donnee utilisateur) : pas d'echappement
_BASE_CSS = Markup((TEMPLATES_DIR / "_base.css").read_text(encoding="utf-8"))
# Le HTML brut est desactive : un contenu legacy ne peut pas injecter de balises
_md = MarkdownIt("commonmark", {"html": False})


def rendre_cv_html(donnees: dict, modele: str = "classique") -> str:
    if modele not in MODELES_CV:
        modele = "classique"
    d = CVData.model_validate(donnees)
    return _env.get_template(f"cv_{modele}.html").render(d=d, base_css=_BASE_CSS)


def rendre_lettre_html(donnees: dict) -> str:
    d = LettreData.model_validate(donnees)
    return _env.get_template("lettre.html").render(d=d, base_css=_BASE_CSS)


def rendre_markdown_html(texte: str) -> str:
    """Rendu des anciens documents (Markdown sans donnees structurees)."""
    corps = _md.render(texte or "")
    return (
        '<!DOCTYPE html><html><head><meta charset="UTF-8"><style>'
        + str(_BASE_CSS)
        + " h1{font-size:20pt} h2{font-size:12pt;margin-top:10pt} ul{list-style:disc;padding-left:16pt}</style>"
        + f"</head><body>{corps}</body></html>"
    )


def cv_en_markdown(donnees: dict) -> str:
    """Apercu Markdown du CV (affiche dans l'application)."""
    d = CVData.model_validate(donnees)
    contact = " | ".join(x for x in (d.contact.email, d.contact.telephone, d.contact.adresse) if x)
    out = [f"# {d.nom}"]
    if d.titre:
        out.append(f"**{d.titre}**")
    if contact:
        out.append(contact)
    if d.resume:
        out += [f"## {d.labels.resume}", d.resume]
    if d.experiences:
        out.append(f"## {d.labels.experience}")
        for e in d.experiences:
            ligne = " | ".join(x for x in (e.poste, e.entreprise, e.lieu, e.date) if x)
            out.append(f"**{ligne}**")
            out += [f"- {p}" for p in e.puces]
    if d.formations:
        out.append(f"## {d.labels.formation}")
        for f in d.formations:
            ligne = " | ".join(x for x in (f.diplome, f.etablissement, f.lieu, f.date) if x)
            out.append(f"**{ligne}**")
            if f.details:
                out.append(f.details)
    if d.competences:
        out.append(f"## {d.labels.competences}")
        for g in d.competences:
            elements = ", ".join(g.elements)
            out.append(f"- **{g.categorie}** : {elements}" if g.categorie else f"- {elements}")
    if d.langues:
        out += [f"## {d.labels.langues}", ", ".join(d.langues)]
    return "\n\n".join(out)


def lettre_en_markdown(donnees: dict) -> str:
    d = LettreData.model_validate(donnees)
    blocs = [d.expediteur_nom, d.expediteur_contact, d.date, d.destinataire]
    parties = ["  \n".join(b.splitlines()) for b in blocs if b]
    if d.objet:
        parties.append(f"**{d.objet}**")
    for texte in (d.salutation, *d.paragraphes, d.formule_finale, d.signature):
        if texte:
            parties.append(texte)
    return "\n\n".join(parties)
