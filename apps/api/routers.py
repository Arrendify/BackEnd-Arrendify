from rest_framework.routers import DefaultRouter
from ..api.views import *
from .Views.arrendadorView import ArrendadorViewSet,  Documentos_Arrendador
from .Views.inmuebles_views import inmueblesViewSet, MobiliarioCantidad
from .Views.inquilinos_view import inquilinosViewSet, DocumentosInquilinoViewSet
from .Views.fiadores_views import AvalViewSet, DocumentosFoo
from .Views.contratos_dash_view import ContratosViewSet
from .Views import fraterna_views
from .Views.investigaciones_views import InvestigacionLaboralViewSet,InvestigacionInquilinoViewSet,InvestigacionFinancieraViewSet,InvestigacionJudicialViewSet
from .Views.stripe_view import *
from .Views.notificaciones_views import NotificacionViewSet
from .Views.reservas_views import ReservaAsadorViewSet, ReservaAsadorFraternaViewSet

# Inicializar router
router = DefaultRouter()

#inquilinos
router.register(r'inquilinos', inquilinosViewSet, basename='inquilino_fiador_obligado')
#Documentos Inquilino
router.register(r'documentos_reg', DocumentosInquilinoViewSet, basename='documentos_reg')
#fiador
router.register(r'aval', AvalViewSet, basename='aval')
router.register(r'documentos_foo', DocumentosFoo, basename='documentos_foo')
#arrendador
router.register(r'arrendadores', ArrendadorViewSet, basename='arrendadores')
router.register(r'arrendadores_documentos', Documentos_Arrendador, basename='documentos_arrendadores')

#Eliminar de cotizador
router.register(r'Arrendador_Cotizador', Arrendador_Cotizador, basename='Arrendador_Cotizacion')

#extras
router.register(r'investigacion', investigaciones, basename='investigaciones')
router.register(r'cotizaciones', Cotizacion_ap, basename='Cotizaciones_ap')

#Investigaciones
router.register(r'investigacion_lab', InvestigacionLaboralViewSet , basename='investigacion_Laboral')
router.register(r'investigacion_inq', InvestigacionInquilinoViewSet, basename='investigacion_Inquilino')
router.register(r'investigacion_fin', InvestigacionFinancieraViewSet, basename= 'investigacion_Financiera')
router.register(r'investigacion_jud', InvestigacionJudicialViewSet, basename= 'investigacion_Judicial')

# Inmuebles
router.register(r'inmuebles', inmueblesViewSet, basename='inmuebles')

# Mobiliario
router.register(r'MobiliarioCantidad', MobiliarioCantidad, basename='MobiliarioCantidad'),
# Recordar password
router.register(r'contrasena', RecuperarPassword, basename='contrasena')
# Contacto
router.register(r'ContactoDatos', ContactoDatos, basename='ContactoDatos'),

# Comentarios
router.register(r'comentarios', Comentario, basename='comentarios'),
# paquetes
router.register(r'paquetes_legales', Paks, basename='paquetes_legales'),
# encuesta
router.register(r'encuesta', Encuestas, basename='encuesta'),
# invetario fotografico
router.register(r'inventario_fotografico', Inventario_fotografico, basename='inventario_fotografico'),

#FRATERNA
router.register(r'residentes', fraterna_views.ResidenteViewSet, basename='residentes')
router.register(r'documentos_residentes', fraterna_views.DocumentosRes, basename='documentos_residentes')
router.register(r'contratos_fraterna', fraterna_views.Contratos_fraterna, basename='contratos_fraterna')
router.register(r'recibos_fraterna', fraterna_views.DocumentosArrendamientosFraterna, basename='recibos_fraterna')
router.register(r'incidencias_fraterna', fraterna_views.IncidenciasFraterna, basename='incidencias_fraterna')
router.register(r'reservas_asador_fraterna', ReservaAsadorFraternaViewSet, basename='reservas_asador_fraterna')

#SEMILLERO PURISIMA
router.register(r'arrendatarios_semillero', fraterna_views.Arrendatarios_semilleroViewSet, basename='arrendatarios_semillero')
router.register(r'documentos_arrendatarios_semillero', fraterna_views.DocumentosArrendatario_semillero, basename='documentos_arrendatarios_semillero')
router.register(r'contratos_semillero', fraterna_views.Contratos_semillero, basename='contratos_semillero')

#GarzaSada
router.register(r'arrendatarios_garzasada', fraterna_views.Arrendatarios_GarzaSadaViewSet, basename='arrendatarios_garzasada')
router.register(r'documentos_arrendatarios_garzasada', fraterna_views.DocumentosArrendatario_GarzaSada, basename='documentos_arrendatarios_garzasada')
router.register(r'contratos_garzasada', fraterna_views.Contratos_GarzaSada, basename='contratos_garzasada')
router.register(r'recibos_garzasada', fraterna_views.DocumentosArrendamiento_GarzaSada, basename='recibos_garzasada')
router.register(r'incidencias_garzasada', fraterna_views.IncidenciasGarzaSada, basename='incidencias_garzasada')
# Reservas de Asador
router.register(r'reservas_asador', ReservaAsadorViewSet, basename='reservas_asador')

# Contratos Dash
router.register(r'contratos_dash', ContratosViewSet, basename='contratos_semillero')
#Stripe
router.register(r'create-checkout-session', CreateStripeCheckoutSession, basename='create-checkout-session')

# Notificaciones de recordatorios de contratos
router.register(r'notificaciones', NotificacionViewSet, basename='notificaciones')



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