# -*- encoding: utf-8 -*-
"""
Copyright (c) 2022 -Jonatan Sepulveda
"""

from django.contrib import admin

from .models import Rol,Profile,Inmuebles


class RolesAdmin(admin.ModelAdmin):
      readonly_fields=('id','created','updated')
admin.site.register(Rol,RolesAdmin)
admin.site.register(Profile)
admin.site.register(Inmuebles)







# Register your models here.
