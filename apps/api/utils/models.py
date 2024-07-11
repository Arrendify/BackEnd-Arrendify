# import del content type y del generic
from django.contrib.contenttypes.models import ContentType
from django.contrib.contenttypes.fields import GenericForeignKey

# django
from django.contrib.auth.models import Group
from django.db.models.query import QuerySet
from django.db import models


#importamos la configuracion para el usuario
from django.conf import settings
User = settings.AUTH_USER_MODEL

#loader model
from swapper import load_model

#Signal
from .signals import notificar

#time zone
from django.utils import timezone



#comportamiento de las notificaciones se manejan con esta calse
class NotificationQueryset(models.QuerySet):
    def leido(self, include_delete = True):
        """
            Retornamos las notificaiones que hayan sido leidas en el actual Queryset
        """
        if include_delete:
            return self.filter(read=True)
        
    def no_leido(self, include_delete = False):
        """
            Retornamos las notificaiones que no hayan sido leidas en el actual Queryset
        """
        if include_delete == True:
            return self.filter(read=False)
        
    def marcar_todo_as_leido(self, destiny = "None"):
        """
        Marcamos todas las notificaciones como leidas en el actual Queryset
        """

        qs = self.read(False)
        if destiny:
            qs = qs.filter(destiny = destiny)
        
        return qs.update(read = True)
    
    def marcar_todo_as_no_leido(self, destiny = "None"):
        """
        Marcamos todas las notificaciones como no leidas en el actual Queryset
        """

        qs = self.read(True)
        if destiny:
            qs = qs.filter(destiny = destiny)
        
        return qs.update(read = False)
    
    


class AbstractNotificacionManager(models.Manager):
    def get_queryset(self):
        return self.NotificationQueryset(self.Model, using = self._db)

class AbstractNotificacion(models.Model):
    pass

    class Levels(models.TextChoices):
        success = 'Success','success'
        info = 'Info','info'
        wrong = 'Wrong', 'wrong'
    
    level = models.CharField(choices=Levels.choices, max_length=20, default=Levels.info)
    
    destiny = models.ForeignKey(User, on_delete=models.CASCADE, related_name='notificaciones', blank=True, null=True)

    actor_content_type = models.ForeignKey(ContentType, related_name='notificar_actor', on_delete=models.CASCADE)
    object_id_actor = models.PositiveIntegerField()
    actor = GenericForeignKey('actor_content_type', 'object_id_actor')

    verbo = models.CharField(max_length=220)

    read = models.BooleanField(default=False)
    publica = models.BooleanField(default=True)
    eliminado = models.BooleanField(default=False)
    
    timestamp = models.DateTimeField(default=timezone.now, db_index=True)

    objects = NotificationQueryset.as_manager()

    class Meta:
        abstract = True
    
    def __str__(self):
        return f'Actor:{self.actor.username} Destino:{self.destiny.username} Verbo:{self.verbo}'
    
        
def notify_signals(verb,**kwargs):
    """
    Funcion de contralador para crear una instancia de notificacion 
    tras una llamada de singnal de accion
    """
    print("ENTRO EN NOTIFY SIGNAL EN EL MODELO")
    print("")
    print("soy el verbo que llega",verb)
    try:
        destiny = kwargs.pop('destiny')
        actor = kwargs.pop('sender')
        print("soy el actor que llega en el modelo",actor)
        print("soy el actor que llega en el modelo y necesito la pk",actor.pk)
        
        publica = bool(kwargs.pop('publica',True))
        timestamp = kwargs.pop('timestamp',timezone.now())
        
        Notify = load_model("api","Notification")
        levels = kwargs.pop('level', Notify.Levels.info)
        
        if isinstance(destiny, Group):
            destinies = destiny.user_set-all()
        
        elif isinstance(destiny, (QuerySet, list)):
            destinies = destiny
        else:
            destinies = [destiny]
            
        new_notify = []
        for destiny in destinies:
            notification = Notify(
                destiny = destiny,
                actor_content_type = ContentType.objects.get_for_model(actor),
                object_id_actor = actor.pk,
                verbo = str(verb),
                publica = publica,
                timestamp = timestamp,
                level = levels   
            )
            
            notification.save()
            new_notify.append(notification)
        print("a continuacion voy a retornar una notificacion nueva")
        return new_notify
    except Exception as e:
            print(f"Error: {e}")  
        
notificar.connect(notify_signals, dispatch_uid='..models.Notification')   
