# -*- coding: utf-8 -*-
"""Crea la cuenta de demostraciones (rol="Demo") y sus residentes ficticios.

La cuenta demo ve la tabla completa de contratos Fraterna con la PII ajena
enmascarada, solo opera contratos propios y genera documentos con la marca
blanca Vivenda (ver apps/api/utils/demo_mode.py). Los dos residentes ficticios
le dan material al picker de "Crear solicitud de contrato" (que para cuentas
no-staff solo muestra residentes propios), de modo que el flujo completo
—solicitud → aprobar → documentos → firma sandbox— corre sin tocar datos reales.

Uso:
    python manage.py create_demo_user
    python manage.py create_demo_user --email correo@dominio.com
    python manage.py create_demo_user --reset-password
"""
import secrets

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand

from apps.home.models import Residentes

USERNAME_DEMO = "demostraciones"
EMAIL_DEMO_DEFAULT = "demostraciones@arrendify.com"

# Datos 100% ficticios; los correos apuntan al buzón de la propia cuenta demo
# (aunque en firma demo los correos se redirigen y el envío automático va
# apagado, así ningún typo alcanza a una persona real).
RESIDENTES_DEMO = (
    {
        'nombre_arrendatario': 'Fernando Cantú Ríos',
        'celular_arrendatario': '8110000001',
        'direccion_arrendatario': 'Av. Roble 402, Col. Valle Alto, Monterrey, N.L.',
        'nombre_residente': 'Diego Cantú Morales',
        'celular_residente': '8110000002',
        'direccion_residente': 'Av. Roble 402, Col. Valle Alto, Monterrey, N.L.',
    },
    {
        'nombre_arrendatario': 'Lucía Garza Elizondo',
        'celular_arrendatario': '8110000003',
        'direccion_arrendatario': 'Calle Cedro 118, Col. Contry, Monterrey, N.L.',
        'nombre_residente': 'Valeria Garza Treviño',
        'celular_residente': '8110000004',
        'direccion_residente': 'Calle Cedro 118, Col. Contry, Monterrey, N.L.',
    },
)


class Command(BaseCommand):
    help = (
        "Crea (o completa) la cuenta de demostraciones: usuario 'demostraciones' "
        "con rol=Demo, is_staff=False y dos residentes ficticios propios."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--email",
            default=EMAIL_DEMO_DEFAULT,
            help=f"Correo de la cuenta demo (default {EMAIL_DEMO_DEFAULT}). "
                 "A este buzón se redirigen los firmantes en las firmas sandbox.",
        )
        parser.add_argument(
            "--reset-password",
            action="store_true",
            help="Si el usuario ya existe, genera y asigna una contraseña nueva.",
        )

    def handle(self, *args, **options):
        User = get_user_model()
        email = options["email"].strip().lower()

        user = User.objects.filter(username=USERNAME_DEMO).first()
        password = None
        if user is None:
            password = secrets.token_urlsafe(16)
            user = User.objects.create_user(
                username=USERNAME_DEMO,
                email=email,
                password=password,
                is_active=True,
                is_staff=False,
                rol="Demo",
            )
            self.stdout.write(self.style.SUCCESS(f"Usuario creado: {USERNAME_DEMO} <{email}>"))
        else:
            cambios = []
            if user.rol != "Demo":
                user.rol = "Demo"
                cambios.append("rol=Demo")
            if user.is_staff:
                user.is_staff = False
                cambios.append("is_staff=False")
            if email and user.email != email:
                user.email = email
                cambios.append(f"email={email}")
            if options["reset_password"]:
                password = secrets.token_urlsafe(16)
                user.set_password(password)
                cambios.append("password nueva")
            if cambios:
                user.save()
                self.stdout.write(self.style.WARNING(
                    f"Usuario {USERNAME_DEMO} ya existía; ajustado: {', '.join(cambios)}"
                ))
            else:
                self.stdout.write(self.style.NOTICE(f"Usuario {USERNAME_DEMO} ya existía; sin cambios."))

        # Residentes ficticios propios (idempotente por nombre+dueño)
        for datos in RESIDENTES_DEMO:
            existente = Residentes.objects.filter(
                user=user, nombre_residente=datos['nombre_residente']
            ).first()
            if existente:
                self.stdout.write(self.style.NOTICE(
                    f"Residente demo ya existe (id={existente.id}): {datos['nombre_residente']}"
                ))
                continue
            residente = Residentes.objects.create(
                user=user,
                nombre_arrendatario=datos['nombre_arrendatario'],
                celular_arrendatario=datos['celular_arrendatario'],
                correo_arrendatario=email,
                direccion_arrendatario=datos['direccion_arrendatario'],
                nombre_residente=datos['nombre_residente'],
                celular_residente=datos['celular_residente'],
                correo_residente=email,
                direccion_residente=datos['direccion_residente'],
            )
            self.stdout.write(self.style.SUCCESS(
                f"Residente demo creado (id={residente.id}): {datos['nombre_residente']}"
            ))

        if password:
            self.stdout.write("")
            self.stdout.write(self.style.WARNING(
                "Contraseña (cópiala ahora; en BD solo queda el hash):"
            ))
            self.stdout.write(f"  {USERNAME_DEMO}  |  {email}  |  {password}")
