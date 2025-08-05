import base64
import logging
import os
from io import BytesIO

from PIL import Image, ImageDraw, ImageFont

logger = logging.getLogger(__name__)


def generate_text_signature(full_name: str, width: int = 500, height: int = 120) -> str:
    """
    Génère une signature automatique avec la police Alex Brush.
    Gère le multiline pour les noms longs et assure la visibilité complète dans le PDF.
    Retourne une data URL base64 de l'image de la signature.
    """
    try:
        # Créer une image avec fond blanc (largeur augmentée pour visibilité complète)
        img = Image.new("RGB", (width, height), "white")
        draw = ImageDraw.Draw(img)

        # Chemin vers la police Alex Brush téléchargée
        alex_brush_path = os.path.join(
            os.path.dirname(__file__), "..", "fonts", "AlexBrush-Regular.ttf"
        )
        font_size = 52  # Taille légèrement augmentée pour Alex Brush
        font = None

        # Essayer de charger Alex Brush en priorité
        if os.path.exists(alex_brush_path):
            try:
                font = ImageFont.truetype(alex_brush_path, font_size)
                logger.info("Police Alex Brush chargée avec succès")
            except Exception as e:
                logger.warning(f"Impossible de charger Alex Brush: {e}")

        # Fallback vers d'autres polices cursives si Alex Brush échoue
        if font is None:
            script_fonts = [
                "/usr/share/fonts/truetype/liberation/LiberationSerif-BoldItalic.ttf",
                "/usr/share/fonts/truetype/dejavu/DejaVuSerif-BoldItalic.ttf",
                "/System/Library/Fonts/Luminari.ttf",
                "/System/Library/Fonts/Chalkduster.ttf",
                "/usr/share/fonts/truetype/liberation/LiberationSerif-Italic.ttf",
                "/usr/share/fonts/truetype/dejavu/DejaVuSerif-Italic.ttf",
            ]

            for font_path in script_fonts:
                try:
                    font = ImageFont.truetype(font_path, font_size)
                    break
                except (OSError, IOError):
                    continue

        # Police par défaut si rien ne fonctionne
        if font is None:
            try:
                font = ImageFont.load_default()
                font_size = 36
            except Exception:
                logger.warning("Police par défaut non disponible")
                font = None

        # Gestion multiline pour les noms longs (comme en frontend)
        max_width = width * 0.85  # Marge de sécurité
        words = full_name.split()
        lines = []

        if font:
            # Essayer d'abord sur une seule ligne
            bbox = draw.textbbox((0, 0), full_name, font=font)
            text_width = bbox[2] - bbox[0]

            if text_width <= max_width:
                # Le nom complet rentre sur une ligne
                lines = [full_name]
            else:
                # Diviser en plusieurs lignes si nécessaire
                if len(words) >= 2:
                    # Essayer prénom(s) + nom sur deux lignes
                    first_parts = words[:-1]  # Tous les prénoms
                    last_name = words[-1]  # Nom de famille

                    first_line = " ".join(first_parts)
                    second_line = last_name

                    # Vérifier que chaque ligne rentre
                    bbox1 = draw.textbbox((0, 0), first_line, font=font)
                    bbox2 = draw.textbbox((0, 0), second_line, font=font)

                    width1 = bbox1[2] - bbox1[0]
                    width2 = bbox2[2] - bbox2[0]

                    if width1 <= max_width and width2 <= max_width:
                        lines = [first_line, second_line]
                    else:
                        # Si ça ne rentre toujours pas, réduire la police
                        while font_size > 24 and (
                            width1 > max_width or width2 > max_width
                        ):
                            font_size -= 2
                            try:
                                font_path = (
                                    alex_brush_path
                                    if os.path.exists(alex_brush_path)
                                    else script_fonts[0]
                                )
                                font = ImageFont.truetype(font_path, font_size)
                                bbox1 = draw.textbbox((0, 0), first_line, font=font)
                                bbox2 = draw.textbbox((0, 0), second_line, font=font)
                                width1 = bbox1[2] - bbox1[0]
                                width2 = bbox2[2] - bbox2[0]
                            except Exception:
                                break
                        lines = [first_line, second_line]
                    # Un seul mot très long - réduire la police
                    while font_size > 20 and text_width > max_width:
                        font_size -= 2
                        try:
                            is_alex_brush = os.path.exists(alex_brush_path)
                            font_path = (
                                alex_brush_path if is_alex_brush else script_fonts[0]
                            )
                            font = ImageFont.truetype(font_path, font_size)
                            bbox = draw.textbbox((0, 0), full_name, font=font)
                            text_width = bbox[2] - bbox[0]
                        except Exception:
                            break
                    lines = [full_name]
        else:
            # Fallback sans police
            lines = [full_name]

        # Dessiner le texte multiline avec Alex Brush
        signature_color = (20, 20, 80)  # Bleu encre élégant
        line_height = font_size + 10  # Espacement entre les lignes
        total_height = len(lines) * line_height - 10  # Hauteur totale du texte

        # Position de départ centrée verticalement
        start_y = (height - total_height) // 2

        for i, line in enumerate(lines):
            if font:
                bbox = draw.textbbox((0, 0), line, font=font)
                text_width = bbox[2] - bbox[0]
                text_height = bbox[3] - bbox[1]
            else:
                text_width = len(line) * (font_size * 0.5)
                text_height = font_size * 0.7

            # Position centrée horizontalement pour chaque ligne
            x = (width - text_width) // 2
            y = start_y + (i * line_height)

            # Dessiner la ligne
            if font:
                draw.text((x, y), line, fill=signature_color, font=font)
            else:
                draw.text((x, y), line, fill=signature_color)

        # Ligne de signature élégante sous la dernière ligne
        last_line_y = start_y + ((len(lines) - 1) * line_height)
        if font and lines:
            bbox = draw.textbbox((0, 0), lines[-1], font=font)
            last_line_width = bbox[2] - bbox[0]
            last_line_height = bbox[3] - bbox[1]
        else:
            last_line_width = len(lines[-1]) * (font_size * 0.5) if lines else 0
            last_line_height = font_size * 0.7

        underline_y = last_line_y + last_line_height + 8
        line_start_x = (width - last_line_width) // 2
        line_end_x = line_start_x + last_line_width

        # Ligne de signature fine
        draw.line(
            [(line_start_x, underline_y), (line_end_x, underline_y)],
            fill=signature_color,
            width=1,
        )

        # Convertir en base64
        buffer = BytesIO()
        img.save(buffer, format="PNG")
        img_data = buffer.getvalue()
        buffer.close()

        # Créer la data URL
        img_base64 = base64.b64encode(img_data).decode("utf-8")
        data_url = f"data:image/png;base64,{img_base64}"

        return data_url

    except Exception as e:
        logger.warning(
            f"Erreur lors de la génération de la signature pour '{full_name}': {e}"
        )
        # Retourner une signature textuelle simple en cas d'erreur
        return generate_simple_text_signature(full_name)


def generate_simple_text_signature(full_name: str) -> str:
    """
    Génère une signature textuelle simple si la génération d'image échoue.
    """
    try:
        # Créer une image simple avec juste le texte
        width, height = 400, 100
        img = Image.new("RGB", (width, height), "white")
        draw = ImageDraw.Draw(img)

        # Utiliser la police par défaut
        try:
            font = ImageFont.load_default()
        except Exception:
            font = None

        # Calculer la position centrée
        if font:
            bbox = draw.textbbox((0, 0), full_name, font=font)
            text_width = bbox[2] - bbox[0]
            text_height = bbox[3] - bbox[1]
        else:
            text_width = len(full_name) * 8
            text_height = 15

        x = (width - text_width) // 2
        y = (height - text_height) // 2

        # Dessiner le texte
        draw.text((x, y), full_name, fill="black", font=font)

        # Ligne de soulignement
        underline_y = y + text_height + 3
        draw.line(
            [(x, underline_y), (x + text_width, underline_y)], fill="black", width=1
        )

        # Convertir en base64
        buffer = BytesIO()
        img.save(buffer, format="PNG")
        img_data = buffer.getvalue()
        buffer.close()

        img_base64 = base64.b64encode(img_data).decode("utf-8")
        return f"data:image/png;base64,{img_base64}"

    except Exception as e:
        logger.error(f"Erreur lors de la génération de signature simple: {e}")
        # En dernier recours, retourner une chaîne vide
        return ""
