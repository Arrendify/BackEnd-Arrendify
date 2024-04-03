import random
import string
from django.db import models
from django.contrib.auth.models import AbstractUser

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
        
