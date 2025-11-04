#!/usr/bin/env python
"""
Script pour uploader les PDFs statiques vers S3/MinIO.

Usage:
    cd backend
    python manage.py shell < scripts/upload_static_pdfs.py

Ou directement :
    python scripts/upload_static_pdfs.py
"""

import os
import django

# Setup Django
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "backend.settings")
django.setup()

from django.core.files.storage import default_storage
from django.core.files.base import ContentFile
from pathlib import Path


def upload_static_pdf(local_path, s3_path):
    """Upload un PDF local vers S3/MinIO."""
    if not os.path.exists(local_path):
        print(f"❌ Fichier introuvable: {local_path}")
        return False

    with open(local_path, "rb") as f:
        content = f.read()

    # Upload vers S3
    default_storage.save(s3_path, ContentFile(content))
    print(f"✅ Uploadé: {local_path} → {s3_path}")

    # Vérifier
    if default_storage.exists(s3_path):
        print(f"   Vérifié: {s3_path} existe dans le storage")
        return True
    else:
        print(f"❌ Échec: {s3_path} n'existe pas après upload")
        return False


def main():
    """Upload tous les PDFs statiques nécessaires."""
    print("📦 Upload des PDFs statiques vers S3/MinIO\n")

    # Chemin vers les fichiers backup
    base_dir = Path(__file__).resolve().parent.parent
    backup_dir = base_dir / "media" / "bails"

    # Liste des fichiers à uploader
    files_to_upload = [
        ("notice_information.pdf", "bails/notice_information.pdf"),
        ("grille_vetuste.pdf", "bails/grille_vetuste.pdf"),
    ]

    success_count = 0
    for local_filename, s3_path in files_to_upload:
        local_path = backup_dir / local_filename
        if upload_static_pdf(str(local_path), s3_path):
            success_count += 1

    print(f"\n✅ {success_count}/{len(files_to_upload)} fichiers uploadés")

    if success_count == len(files_to_upload):
        print("\n🎉 Tous les PDFs statiques sont uploadés !")
        print("Tu peux maintenant accéder aux notices et grilles dans l'app.")
    else:
        print("\n⚠️  Certains fichiers n'ont pas pu être uploadés.")
        print("Vérifie que les fichiers existent dans backend/media/bails/")


if __name__ == "__main__":
    main()
