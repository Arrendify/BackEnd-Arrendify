# Generated by Django 3.2.6 on 2023-12-19 18:22

import apps.home.models
from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ('home', '0004_encuesta'),
    ]

    operations = [
        migrations.CreateModel(
            name='Inventario_foto',
            fields=[
                ('id', models.AutoField(primary_key=True, serialize=False)),
                ('inv_fotografico', models.FileField(upload_to=apps.home.models.Inventario_foto.get_inv_upload_path)),
                ('dateTimeOfUpload', models.DateTimeField(auto_now=True)),
                ('paquete_asociado', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.CASCADE, related_name='paq_asociado', to='home.paquetes')),
                ('user', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, to=settings.AUTH_USER_MODEL)),
            ],
            options={
                'db_table': 'inventario_fotografico',
            },
        ),
    ]
