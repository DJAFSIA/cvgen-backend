import os
import tempfile

async def generer_pdf(contenu_texte: str, nom_fichier: str) -> str:
    try:
        from weasyprint import HTML

        html_contenu = f"""
        <!DOCTYPE html>
        <html lang="fr">
        <head>
          <meta charset="UTF-8">
          <style>
            body {{
              font-family: Arial, sans-serif;
              font-size: 12px;
              line-height: 1.6;
              color: #333;
              margin: 40px;
            }}
            h1 {{ font-size: 20px; color: #2c3e50; margin-bottom: 4px; }}
            h2 {{ font-size: 15px; color: #534AB7; border-bottom: 1px solid #eee; padding-bottom: 4px; }}
            h3 {{ font-size: 13px; color: #333; }}
            p {{ margin: 6px 0; }}
            .section {{ margin-bottom: 18px; }}
          </style>
        </head>
        <body>
          <div class="section">
            {contenu_texte.replace(chr(10), '<br>')}
          </div>
        </body>
        </html>
        """

        dossier_tmp = tempfile.gettempdir()
        chemin = os.path.join(dossier_tmp, nom_fichier)
        HTML(string=html_contenu).write_pdf(chemin)
        return chemin

    except ImportError:
        raise RuntimeError(
            "WeasyPrint n'est pas installé. "
            "Exécutez : pip install weasyprint"
        )
