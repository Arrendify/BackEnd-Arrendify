#Django
from .utils.models import AbstractNotificacion
from django.db import models

# Create your models here.


class Notification(AbstractNotificacion):
    
    class Meta(AbstractNotificacion.Meta):
        abstract = False

