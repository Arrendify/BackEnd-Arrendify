from django import forms
from .models import Inmuebles, Inquilino, Arrendador, ImagenInmueble, Fiador_obligado
from django.forms import ClearableFileInput

class InmueblesForm(forms.ModelForm):    
    class Meta:
        model = Inmuebles
        fields = '__all__'

class InquilinosForm(forms.ModelForm):    
    class Meta:
        model = Inquilino
        fields = '__all__'

class ImagenInmuelbeForm(forms.ModelForm):    
    class Meta:
        model = ImagenInmueble
        fields = ['imagenes',]
    widgets = {
            'imagenes': ClearableFileInput(attrs={'multiple': True}),
        }

class ArrendadorForm(forms.ModelForm):    
    class Meta:
        model = Arrendador
        fields = '__all__'

class FiadorForm(forms.ModelForm):    
    class Meta:
        model = Fiador_obligado
        fields = '__all__'