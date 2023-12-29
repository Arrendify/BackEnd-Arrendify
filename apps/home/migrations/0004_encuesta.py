# Generated by Django 3.2.6 on 2023-12-18 16:55

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('home', '0003_cotizacion_user'),
    ]

    operations = [
        migrations.CreateModel(
            name='Encuesta',
            fields=[
                ('id', models.AutoField(primary_key=True, serialize=False)),
                ('pregunta1', models.CharField(blank=True, max_length=100, null=True)),
                ('pregunta2', models.CharField(blank=True, max_length=100, null=True)),
                ('pregunta3', models.CharField(blank=True, max_length=100, null=True)),
                ('pregunta4', models.CharField(blank=True, max_length=100, null=True)),
                ('pregunta5', models.CharField(blank=True, max_length=100, null=True)),
                ('pregunta6', models.CharField(blank=True, max_length=100, null=True)),
            ],
            options={
                'db_table': 'encuesta',
            },
        ),
    ]
