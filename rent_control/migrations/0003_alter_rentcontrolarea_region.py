# Generated by Django 5.1.7 on 2025-03-28 22:38

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('rent_control', '0002_rentcontrolarea_quartier_id'),
    ]

    operations = [
        migrations.AlterField(
            model_name='rentcontrolarea',
            name='region',
            field=models.CharField(choices=[('PARIS', 'Paris'), ('EST_ENSEMBLE', 'Est Ensemble'), ('PLAINE_COMMUNE', 'Plaine Commune'), ('LYON', 'Lyon'), ('MONTPELLIER', 'Montpellier'), ('BORDEAUX', 'Bordeaux'), ('LILLE', 'Lille'), ('PAYS_BASQUE', 'Pays Basque')], max_length=20),
        ),
    ]
