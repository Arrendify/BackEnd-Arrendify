# Generated by Django 3.2.6 on 2023-12-28 22:46

from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('home', '0005_inventario_foto'),
    ]

    operations = [
        migrations.RemoveField(
            model_name='encuesta',
            name='pregunta5',
        ),
        migrations.RemoveField(
            model_name='encuesta',
            name='pregunta6',
        ),
    ]