from django.apps import AppConfig

class HomeAppConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'apps.home'
    verbose_name = 'home'

    def ready(self): #  Se ejecuta cuando la aplicación está lista
        print("Esta en apps.py ")
        # Código adicional que deseas ejecutar cuando la aplicación esté lista
        from . import scheduler # Esta línea importa el módulo
        # Asegura job diario 09:00 (hora local) para verificación de contratos
        if hasattr(scheduler, 'ensure_scheduler_started'):
            scheduler.ensure_scheduler_started()
        # Scheduler adicional para tareas previas del proyecto
        scheduler.start_scheduler_notificaciones() #inicia el scheduler de notificaciones

default_app_config = 'home.apps.HomeAppConfig'
