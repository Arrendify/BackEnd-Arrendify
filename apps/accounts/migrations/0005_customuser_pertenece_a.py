# Generated by Django 3.2.6 on 2024-02-16 18:35

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('accounts', '0004_alter_customuser_name_inmobiliaria'),
    ]

    operations = [
        migrations.AddField(
            model_name='customuser',
            name='pertenece_a',
            field=models.CharField(blank=True, max_length=100, null=True),
        ),
    ]