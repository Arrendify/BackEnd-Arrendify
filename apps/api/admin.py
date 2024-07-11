from django.contrib import admin

# Register your models here.

#Django

from .utils.admin import AbstractNotifyAdmin
from .models import Notification

admin.site.register(Notification, AbstractNotifyAdmin)
