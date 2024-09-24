from rest_framework.routers import DefaultRouter
from ..api.views import *
from .Views.arrendador.arrendadorView import ArrendadorViewSet, Arrendador_inmuebles


# router = routers.SimpleRouter()
# router.register(r'users', ListarLibrosSet, basename='user')
# urlpatterns += router.urls

router = DefaultRouter()

#inquilinos
router.register(r'inquilino_fiador_obligado', InquilinoFiadorObligadoViewSet, basename='inquilino_fiador_obligado')
router.register(r'inquilinos_fiadores', Inquilinos_fiadores, basename='inquilino_fiadores')
router.register(r'documentos_reg', DocumentosInquilino, basename='documentos_reg')
router.register(r'fiadores_obligados', Fiador_obligadoViewSet, basename='fiadores_obligados')
router.register(r'documentos_foo', DocumentosFoo, basename='documentos_foo')
#arrendador
router.register(r'arrendadores', ArrendadorViewSet, basename='arrendadores')
router.register(r'Arrendador_Cotizador', Arrendador_Cotizador, basename='Arrendador_Cotizacion')
router.register(r'HistorialDocumentosArrendadorViewSet', HistorialDocumentosArrendadorViewSet, basename='HistorialDocumentosArrendadorViewSet'),
#extras
router.register(r'investigacion', investigaciones, basename='investigaciones')
router.register(r'cotizaciones', Cotizacion_ap, basename='Cotizaciones_ap')

# Inmuebles
router.register(r'inmuebles', inmueblesViewSet, basename='inmuebles')
router.register(r'arrendador_inmuebles', Arrendador_inmuebles, basename='arrendador_inmuebles')
# Mobiliario
router.register(r'MobiliarioCantidad', MobiliarioCantidad, basename='MobiliarioCantidad'),
# Recordar password
router.register(r'contrasena', RecuperarPassword, basename='contrasena')
# Contacto
router.register(r'ContactoDatos', ContactoDatos, basename='ContactoDatos'),

# Comentarios
router.register(r'comentarios', Comentario, basename='comentarios'),
# paquetes
router.register(r'paquetes', Paks, basename='paquetes'),
# encuesta
router.register(r'encuesta', Encuestas, basename='encuesta'),# encuesta
# invetario fotografico
router.register(r'inventario_fotografico', Inventario_fotografico, basename='inventario_fotografico'),

#FRATERNA
router.register(r'residentes', fraterna_views.ResidenteViewSet, basename='residentes')
router.register(r'documentos_residentes', fraterna_views.DocumentosRes, basename='documentos_residentes')
router.register(r'contratos_fraterna', fraterna_views.Contratos_fraterna, basename='contratos_fraterna')

#SEMILLERO PURISIMA
router.register(r'arrendatarios_semillero', fraterna_views.Arrendatarios_semilleroViewSet, basename='arrendatarios_semillero')
router.register(r'documentos_arrendatarios_semillero', fraterna_views.DocumentosArrendatario_semillero, basename='documentos_arrendatarios_semillero')
router.register(r'contratos_semillero', fraterna_views.Contratos_semillero, basename='contratos_semillero')

# si descomentamos la linea de abajo nos da el create con post de notificacion directo con el metodo notify_signals.

# router.register(r'notis_prueba', notis_prueba, basename='notis_prueba')
# router.register(r'documentos_foo', DocumentosFoo, basename='documentos_foo')
# router.register(r'i_a', Inmuebles_a, basename='a_a')


# router.register(r'ListarInmuieblesImagenesArrendador', ListarInmuieblesImagenesArrendador, basename='ListarInmuieblesImagenesArrendador')

# Cambiar a v1/

# myobjects_list = ArrendadorViewSet.as_view({
#     'get': 'list',
#     'get': 'retrieve'
# })