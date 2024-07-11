#Django
from typing import Any
from django.contrib import admin
from django.db.models.query import QuerySet
from django.http import HttpRequest

class AbstractNotifyAdmin(admin.ModelAdmin):
    raw_id_fields = ('destiny',)
    list_display = ("destiny","actor","verbo", "read", "publica")
    list_filter = ("level","read")

    def get_queryset(self, request):
        qs = super(AbstractNotifyAdmin, self).get_queryset(request)

        return qs.prefetch_related("actor")