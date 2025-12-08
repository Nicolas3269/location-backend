"""
Migration pour convertir etage de CharField vers IntegerField.
Stratégie: colonne intermédiaire pour éviter les problèmes de conversion.
"""

from django.db import migrations, models


def copy_etage_to_new(apps, schema_editor):
    """Copie et convertit etage → etage_new."""
    Bien = apps.get_model("location", "Bien")
    HistoricalBien = apps.get_model("location", "HistoricalBien")

    for Model in [Bien, HistoricalBien]:
        for obj in Model.objects.all():
            if obj.etage and obj.etage.strip():
                try:
                    obj.etage_new = int(obj.etage)
                except ValueError:
                    obj.etage_new = None
            else:
                obj.etage_new = None
            obj.save(update_fields=["etage_new"])


def copy_etage_back(apps, schema_editor):
    """Reverse: copie etage_new → etage."""
    Bien = apps.get_model("location", "Bien")
    HistoricalBien = apps.get_model("location", "HistoricalBien")

    for Model in [Bien, HistoricalBien]:
        for obj in Model.objects.all():
            obj.etage = str(obj.etage_new) if obj.etage_new is not None else ""
            obj.save(update_fields=["etage"])


class Migration(migrations.Migration):

    dependencies = [
        ("location", "0022_remove_bien__adresse_legacy_and_more"),
    ]

    operations = [
        # 1. Créer nouvelle colonne integer
        migrations.AddField(
            model_name="bien",
            name="etage_new",
            field=models.IntegerField(blank=True, null=True, default=None),
        ),
        migrations.AddField(
            model_name="historicalbien",
            name="etage_new",
            field=models.IntegerField(blank=True, null=True, default=None),
        ),
        # 2. Copier les données
        migrations.RunPython(copy_etage_to_new, copy_etage_back),
        # 3. Supprimer ancienne colonne
        migrations.RemoveField(model_name="bien", name="etage"),
        migrations.RemoveField(model_name="historicalbien", name="etage"),
        # 4. Renommer nouvelle colonne
        migrations.RenameField(
            model_name="bien", old_name="etage_new", new_name="etage"
        ),
        migrations.RenameField(
            model_name="historicalbien", old_name="etage_new", new_name="etage"
        ),
        # 5. Appliquer les options finales
        migrations.AlterField(
            model_name="bien",
            name="etage",
            field=models.IntegerField(
                blank=True,
                default=None,
                help_text="0=RDC, 1=1er étage, etc.",
                null=True,
                verbose_name="Étage",
            ),
        ),
        migrations.AlterField(
            model_name="historicalbien",
            name="etage",
            field=models.IntegerField(
                blank=True,
                default=None,
                help_text="0=RDC, 1=1er étage, etc.",
                null=True,
                verbose_name="Étage",
            ),
        ),
    ]
