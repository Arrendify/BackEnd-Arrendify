import random
import string
from django.db import models
from django.contrib.auth.models import AbstractUser
#time zone
from django.utils import timezone

#buit-in signals
from django.db.models.signals import post_save

#signals
from ..api.utils.signals import notificar

class CustomUser(AbstractUser):
    rol = models.CharField(max_length=100, default = "Normal")
    name_inmobiliaria = models.CharField(max_length=100, unique=True, null=True, blank=True)
    code_inmobiliaria =  models.CharField(max_length=9, editable = False, unique=True,null=True, blank=True)
    pertenece_a = models.CharField(max_length=100, null=True, blank=True)

    def save(self, *args, **kwargs):
        print("ni siquiera se si entro")
        if self.rol == "Inmobiliaria":
            characters = string.ascii_letters + string.digits
            length = 4
            name = str(self.name_inmobiliaria[0:3])
            print(characters)
            print(name)
            self.code_inmobiliaria = 'AL' + ''.join(random.choice(characters) for _ in range(length)).upper() + name.upper()
            print(self.code_inmobiliaria)
            print("ya voy a salvar")
            super().save(*args, **kwargs) 
        else:
            print("soy agente o usuario normal")
            super().save(*args, **kwargs)

class Post(models.Model):
    user = models.ForeignKey(CustomUser, on_delete=models.CASCADE, related_name='usuario_post')
    title = models.CharField(max_length=100)
    image = models.FileField(upload_to ='notificaciones', null=True, blank=True) 
    text = models.TextField()
    url = models.TextField()
    timestamp = models.DateTimeField(default = timezone.now, db_index=True)
    
    def __str__(self):
        return self.title
        
    
def notify_post(sender, instance, created, actor=None, **kwargs):
    if created:
        print("instance.user", instance.user)
        print("instance.title", instance.title)
        print("cambiar el destiny", instance.user)
        print("actor en notify_post",actor)
        print("instance solo", instance)
        if actor is None:
            actor = instance.user  # Si no se proporciona un actor, usar instance.user como predeterminado
        notificar.send(sender=actor, destiny=instance.user, verb=instance.title, level="success")
    else:
        print("no se creo ni madres")
    
    
post_save.connect(notify_post, sender= Post)
