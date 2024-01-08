# -*- encoding: utf-8 -*-
"""
Copyright (c) 2019 - present AppSeed.us
"""

from django import template
from django.contrib.auth.decorators import login_required
from django.contrib.auth.mixins import UserPassesTestMixin, LoginRequiredMixin
from django.http import HttpResponse, HttpResponseRedirect
from django.template import loader
from django.urls import reverse
from requests import get

from django.shortcuts import redirect, render, get_object_or_404

# //////////////////////////////////////
# paths 
# //////////////////////////////////////


def index(request):
    remote_ip = request.META.get('REMOTE_ADDR')
    print("IP VISITANTE INDEX: ",remote_ip)
    context = {'segment': 'index'}
    html_template = loader.get_template('home/page-404.html')
    return HttpResponse(html_template.render(context, request))

#================INQUILINOS=================
def path_inq(request):
    return render(request, 'home/inquilinos/inquilinos.html', {
    })
def path_inq_detalles(request,id):
    return render(request, 'home/inquilinos/detalles_inquilino.html', {
    })
def path_inq_edit(request,id):
    return render(request, 'home/inquilinos/edit_inq.html', {
    })

#================FIADORES=================
def path_foo(request):
    return render(request, 'home/Fiador/Foo.html', {
    })
def path_foo_detalles(request,slug):
    return render(request, 'home/Fiador/detalles_foo.html', {
    })
def path_foo_edit(request,id):
    return render(request, 'home/Fiador/edit_foo.html', {
    })    
 
def path_inmuebles(request):
    return render(request, 'home/inmuebles.html', {
    })   

def pages(request):
    context = {}
    # All resource paths end in .html.
    # Pick out the html file name from the url. And load that template.
    try:

        load_template = request.path.split('/')[-1]
        if load_template == 'admin':
            return HttpResponseRedirect(reverse('admin:index'))
        context['segment'] = load_template

        html_template = loader.get_template('home/' + load_template)
        return HttpResponse(html_template.render(context, request))

    except template.TemplateDoesNotExist:

        html_template = loader.get_template('home/page-404.html')
        return HttpResponse(html_template.render(context, request))

    except:
        html_template = loader.get_template('home/page-500.html')
        return HttpResponse(html_template.render(context, request))
