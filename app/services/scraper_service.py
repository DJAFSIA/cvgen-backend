import trafilatura
import requests

async def extraire_texte_offre_url(url: str) -> str:
    """Récupère le texte d'une offre en simulant un vrai navigateur."""
    try:
        # Headers pour faire croire qu'on est un humain sur Chrome
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8",
            "Accept-Language": "fr-FR,fr;q=0.9,en-US;q=0.8,en;q=0.7",
        }

        # On télécharge la page manuellement avec requests
        response = requests.get(url, headers=headers, timeout=15)
        
        if response.status_code != 200:
            return f"Erreur : Le site bloque l'accès (Code {response.status_code})."

        # On donne le contenu HTML à trafilatura pour extraire le texte propre
        texte = trafilatura.extract(response.text, include_comments=False)
        
        if texte:
            return texte
        return "Erreur : Le contenu de l'offre est vide ou illisible."
        
    except Exception as e:
        return f"Erreur lors de l'extraction : {str(e)}"