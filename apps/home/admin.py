# -*- encoding: utf-8 -*-
"""
Copyright (c) 2022 -Jonatan Sepulveda
"""

from django.contrib import admin
from .forms import InquilinosForm, InmueblesForm, ArrendadorForm
from .models import Rol,Profile,Inmuebles,ImagenInmueble

class ImagenInmuebleAdmin(admin.TabularInline):
      model = ImagenInmueble


class InmuebleAdmin(admin.ModelAdmin):
      list_display=["alias","tipo_inmueble"]
      form = InquilinosForm
      inlines = [
            ImagenInmuebleAdmin
      ]

class RolesAdmin(admin.ModelAdmin):
      readonly_fields=('id','created','updated')
admin.site.register(Rol,RolesAdmin)
admin.site.register(Profile)
admin.site.register(Inmuebles)
admin.site.register(ImagenInmueble)






# Register your models here.
