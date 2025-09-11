from django.apps import AppConfig
import os, sys, logging

class HomeAppConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'apps.home'
    verbose_name = 'home'

    def ready(self):
        print("Esta en apps.py (HomeAppConfig.ready)")
        # No correr en comandos administrativos
        if any(c in sys.argv for c in {'makemigrations','migrate','collectstatic','shell','test','loaddata','dumpdata'}):
            return
        # Evita doble arranque (autoreload / gunicorn)
        is_reload = os.environ.get('RUN_MAIN') == 'true'
        is_gunicorn = 'gunicorn' in os.environ.get('SERVER_SOFTWARE','').lower() or os.environ.get('GUNICORN_CMD_ARGS')
        if is_reload or is_gunicorn:
            from . import scheduler
            if hasattr(scheduler, 'ensure_scheduler_started'):
                scheduler.ensure_scheduler_started()
            logging.getLogger(__name__).warning("✅ APScheduler inicializado")