"""Photo du CV : verifiee, recadree et reencodee a l'arrivee.

Le fichier recu n'est jamais garde tel quel : l'image est decodee puis reecrite en JPEG au format
d'une photo d'identite (35 x 45 mm a 300 ppp). Le reencodage supprime toutes les metadonnees
(position GPS, appareil, date) et neutralise un fichier piege.
"""
import warnings
from io import BytesIO

from PIL import Image, ImageOps, UnidentifiedImageError

MAX_OCTETS = 8 * 1024 * 1024
LARGEUR, HAUTEUR = 413, 531  # 35 x 45 mm a 300 ppp
LARGEUR_MIN, HAUTEUR_MIN = 200, 250
PIXELS_MAX = 50_000_000
FORMATS = ("JPEG", "PNG", "WEBP")


class PhotoInvalide(ValueError):
    """Image refusee ; le code correspond a un message traduit sur le site."""

    def __init__(self, code: str):
        super().__init__(code)
        self.code = code


def normaliser(contenu: bytes) -> bytes:
    """JPEG 413 x 531, oriente et sans metadonnees ; PhotoInvalide si l'image ne convient pas."""
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("error", Image.DecompressionBombWarning)
            image = Image.open(BytesIO(contenu), formats=FORMATS)
            # Dimensions lues dans l'en-tete, avant tout decodage (image geante compressee)
            if image.width * image.height > PIXELS_MAX:
                raise PhotoInvalide("photo_too_large")
            if image.width < LARGEUR_MIN or image.height < HAUTEUR_MIN:
                raise PhotoInvalide("photo_too_small")
            image = ImageOps.exif_transpose(image)
            if image.mode != "RGB":
                # Fond blanc sous une image transparente
                calque = image.convert("RGBA")
                fond = Image.new("RGBA", calque.size, (255, 255, 255, 255))
                image = Image.alpha_composite(fond, calque).convert("RGB")
    except PhotoInvalide:
        raise
    except (UnidentifiedImageError, Image.DecompressionBombError, Image.DecompressionBombWarning, OSError, ValueError, SyntaxError) as e:
        raise PhotoInvalide("photo_invalid") from e

    # Recadrage au format 35 x 45, cadre un peu au-dessus du centre (visage)
    image = ImageOps.fit(image, (LARGEUR, HAUTEUR), method=Image.Resampling.LANCZOS, centering=(0.5, 0.4))
    sortie = BytesIO()
    image.save(sortie, "JPEG", quality=87, optimize=True)  # ni EXIF, ni profil : aucun argument ne les reprend
    return sortie.getvalue()
