# Generated by Django 5.1.7 on 2025-03-28 21:10

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('rent_control', '0001_initial'),
    ]

    operations = [
        migrations.AddField(
            model_name='rentcontrolarea',
            name='quartier_id',
            field=models.CharField(blank=True, max_length=20, null=True),
        ),
    ]
