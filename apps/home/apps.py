from django.apps import AppConfig

class HomeAppConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'apps.home'
    verbose_name = 'home'

    def ready(self): #  Se ejecuta cuando la aplicación está lista
        print("Esta en apps.py ")
        # Código adicional que deseas ejecutar cuando la aplicación esté lista
        from . import scheduler # Esta línea importa el módulo
       # scheduler.start_scheduler() #inicia el scheduler
        scheduler.start_scheduler_notificaciones() #inicia el scheduler de notificaciones

default_app_config = 'home.apps.HomeAppConfig'
