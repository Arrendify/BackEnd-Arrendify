import secrets
from pathlib import Path

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand
from django.utils import timezone

# Usuarios solicitados: username = parte local del correo (antes de @)
FRATERNA_EMAILS = (
    "kgonzalez@fraterna.mx",
    "xmancillas@fraterna.mx",
    "erodriguez@fraterna.mx",
)


class Command(BaseCommand):
    help = (
        "Crea usuarios Fraterna: pertenece_a=Fraterna, username=parte local del email, "
        "contraseñas aleatorias. Por defecto is_staff=True para que el API actual "
        "(sin desplegar cambios en fraterna_views) les deje ver contratos/residentes. "
        "Usa --no-staff si ya reconocéis pertenece_a en el backend."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--no-staff",
            action="store_true",
            help="No asignar is_staff (solo si el backend ya trata pertenece_a=Fraterna).",
        )
        parser.add_argument(
            "--escribir-credenciales",
            metavar="RUTA",
            nargs="?",
            const="fraterna_operadores_credenciales.txt",
            default=None,
            help=(
                "Ruta del archivo donde guardar credenciales en texto plano "
                "(por defecto fraterna_operadores_credenciales.txt en el cwd). "
                "No lo subas a git ni lo compartas en canales inseguros."
            ),
        )

    def handle(self, *args, **options):
        User = get_user_model()
        creds = []
        give_staff = not options["no_staff"]

        for raw in FRATERNA_EMAILS:
            email = raw.strip().lower()
            local, _, domain = email.partition("@")
            if not local or not domain:
                self.stderr.write(self.style.ERROR(f"Email inválido: {raw!r}"))
                continue

            username = local
            if User.objects.filter(username=username).exists():
                self.stdout.write(
                    self.style.WARNING(f"Ya existe username={username!r}, se omite.")
                )
                continue

            password = secrets.token_urlsafe(16)
            User.objects.create_user(
                username=username,
                email=email,
                password=password,
                is_active=True,
                is_staff=give_staff,
                pertenece_a="Fraterna",
            )
            creds.append((username, email, password))
            staff_note = " (staff)" if give_staff else ""
            self.stdout.write(
                self.style.SUCCESS(f"Creado: {username} <{email}>{staff_note}")
            )

        if creds:
            self.stdout.write("")
            self.stdout.write(
                self.style.WARNING(
                    "Contraseñas (cópialas ahora; en BD solo queda el hash):"
                )
            )
            for username, email, password in creds:
                self.stdout.write(f"  {username}  |  {email}  |  {password}")

            out_path = options.get("escribir_credenciales")
            if out_path:
                path = Path(out_path).resolve()
                lines = [
                    "# Credenciales generadas por create_fraterna_operadores",
                    "# NO versionar; no enviar por chat/email sin cifrar.",
                    f"# Generado: {timezone.now().isoformat()}",
                    "# Formato: username|email|password",
                    "",
                ]
                for username, email, password in creds:
                    lines.append(f"{username}|{email}|{password}")
                path.write_text("\n".join(lines) + "\n", encoding="utf-8")
                self.stdout.write("")
                self.stdout.write(
                    self.style.SUCCESS(f"Credenciales guardadas en: {path}")
                )
        else:
            self.stdout.write(
                self.style.NOTICE(
                    "No se creó ningún usuario nuevo (los username ya existían u hubo emails inválidos)."
                )
            )
