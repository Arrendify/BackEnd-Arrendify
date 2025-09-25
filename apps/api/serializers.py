from rest_framework import serializers
from ..home.models import *
from ..authentication.models import *
from ..authentication.serializers import User2Serializer
from .models import Notification
from ..accounts.models import *
from django.conf import settings

class DFSerializer(serializers.ModelSerializer):
    aval_nombre = serializers.CharField(source='aval.nombre_completo', read_only=True)
    class Meta:
        model = DocumentosFiador
        fields = '__all__'
class DISerializer(serializers.ModelSerializer):
    inquilinos_nombre = serializers.CharField(source='arrendatario.nombre_completo', read_only=True)
    class Meta:
        model = DocumentosInquilino
        fields = '__all__'

class AvalSerializer(serializers.ModelSerializer):
    arrendatario_nombre_completo = serializers.CharField(source='inquilino.nombre_completo', read_only=True)
    empresa_nombre= serializers.CharField(source='inquilino.nombre_empresa', read_only=True)
    archivos = DFSerializer(many=True, read_only=True)
    user =  User2Serializer(read_only=True)
    class Meta:
        model = Aval
        #model = Fiador_obligado
        fields = '__all__'   

class InquilinoSerializers(serializers.ModelSerializer):
    # aval = Fiador_obligadoSerializer(many=True, read_only=True)
    aval = AvalSerializer(many=True, read_only=True)
    archivos = DISerializer(many=True, read_only=True)
    user =  User2Serializer(read_only=True)
    
    class Meta:
        #model = Inquilino
        model = Arrendatario
        fields = '__all__'


#arrendador


# Documentos Arrendador
class DocumentosArrendadorSerializer(serializers.ModelSerializer):
    class Meta:
        model = DocumentosArrendador
        fields = '__all__'

#inmuebles
class InmueblesMobiliarioSerializer(serializers.ModelSerializer):
    class Meta:
        model = InmueblesInmobiliario
        fields = ('cantidad', 'mobiliario','observaciones','inmuebles')
        #fields = '__all__'

class DocumentosInmuebleSerializer(serializers.ModelSerializer):
    class Meta:
        model = DocumentosInmueble
        fields = '__all__'
        
class InmueblesSerializer(serializers.ModelSerializer):
    #nombre_empresa= serializers.CharField(source='propietario.nombre_empresa', read_only=True)
    #nombre_completo= serializers.CharField(source='propietario.nombre_completo', read_only=True)
    documentos_inmueble = DocumentosInmuebleSerializer(many=True, read_only=True)
    mobiliario = InmueblesMobiliarioSerializer(many=True, read_only=True)
    class Meta:
        model = Inmuebles
        fields = '__all__'


# Comentario 
class UserSerializer2(serializers.ModelSerializer):
    class Meta:
        model = CustomUser
        fields = ('username', 'first_name', 'email', 'is_staff')

# Arrendador
class ArrendadorSerializer(serializers.ModelSerializer):
    archivos = DocumentosArrendadorSerializer(many=True, read_only=True)
    inmuebles_set = InmueblesSerializer(many=True, read_only = True)
    user =  User2Serializer(read_only=True)
    class Meta:
        #model = Arrendador
        model = Propietario
        fields = '__all__'
        


class InvestigacionSerializers(serializers.ModelSerializer):
    # inquilino = serializers.PrimaryKeyRelatedField(queryset=Arrendatario.objects.all())
    inquilino = InquilinoSerializers(read_only=True)
 
    class Meta:
        model = Investigacion
        fields = '__all__'


#------------------------------Investigaciones Independientes ---------------------------------               
class DocumentosLaboralSerializer(serializers.ModelSerializer):

    class Meta:
        model = DocumentosLaboral
        fields = '__all__'
        
class InvestigacionLaboralSerializer(serializers.ModelSerializer):
    prospecto_nombre= serializers.CharField(source='Investigacion_Laboral.nombre_completo', read_only=True)
    archivos = DocumentosLaboralSerializer(many=True, read_only=True)
    user =  User2Serializer(read_only=True)
    class Meta:
        model = Investigacion_Laboral
        fields = '__all__'

class DocumentosJudicialSerializer(serializers.ModelSerializer):

    class Meta:
        model = DocumentosJudicial
        fields = '__all__'
              
class InvestigacionJudicialSerializer(serializers.ModelSerializer):
    prospecto_nombre= serializers.CharField(source='Investigacion_Judicial.nombre_completo', read_only=True)
    empresa_nombre= serializers.CharField(source='Investigacion_Judicial.nombre_empresa', read_only=True)
    archivos = DocumentosJudicialSerializer(many=True, read_only=True)
    user =  User2Serializer(read_only=True)
    class Meta:
        model = Investigacion_Judicial
        fields ='__all__'

class DocumentosFinancieraSerializer(serializers.ModelSerializer):

    class Meta:
        model = DocumentosFinanciera
        fields = '__all__'
          
class InvestigacionFinancieraSerializer(serializers.ModelSerializer):
    prospecto_nombre= serializers.CharField(source='Investigacion_Financiera.nombre_completo', read_only=True)
    empresa_nombre= serializers.CharField(source='Investigacion_Financiera.nombre_empresa', read_only=True)
    archivos = DocumentosFinancieraSerializer(many=True, read_only=True)
    user =  User2Serializer(read_only=True)
    class Meta:
        model = Investigacion_Financiera
        fields ='__all__'
        
class DocumentosInvInquilinoSerializer(serializers.ModelSerializer):

    class Meta:
        model = DocumentosInvInquilino
        fields = '__all__'
        
class InvestigacionInquilinoSerializer(serializers.ModelSerializer):
    prospecto_nombre= serializers.CharField(source='Investigacion_Inquilino.nombre_completo', read_only=True)
    empresa_nombre= serializers.CharField(source='Investigacion_Inquilino.nombre_empresa', read_only=True)
    archivos = DocumentosInvInquilinoSerializer(many=True, read_only=True)
    user =  User2Serializer(read_only=True)
    class Meta:
        model = Investigacion_Inquilino
        fields = '__all__'
    
#------------------------------Fin Investigaciones Independientes ---------------------------------   


class CotizacionSerializers(serializers.ModelSerializer):
    datos_inmueble = InmueblesSerializer(read_only=True, source='inmueble')
    datos_arrendador = ArrendadorSerializer(read_only=True, source='arrendador')
    cot_inquilino = InquilinoSerializers(read_only=True, source='inquilino')
    #agentify = InquilinoSerializers(read_only=True, source='agentify')
    
    class Meta:
        model = Cotizacion
        fields = '__all__'

class Cotizacion_genSerializer(serializers.ModelSerializer):
    class Meta:
        model = Cotizacion_gen
        fields = '__all__' 

class ComentarioSerializer(serializers.ModelSerializer):
    #user = User2Serializer(read_only=True)
    user = UserSerializer2(read_only=True)  # Campo solo de lectura para mostrar los datos del usuario
    # user_id = serializers.PrimaryKeyRelatedField(queryset=User.objects.all(), write_only=True, source='user')  # Campo de escritura para insertar el ID del usuario
    class Meta:
        model = Comentario
        fields = '__all__'
        
class CotizacionSerializerPagares(serializers.ModelSerializer):
    datos_inmueble = InmueblesSerializer(read_only=True, source='inmueble')
    datos_arrendador = ArrendadorSerializer(read_only=True, source='arrendador')
    cot_inquilino = InquilinoSerializers(read_only=True, source='inquilino')
    
    class Meta:
        model = Cotizacion
        fields = '__all__'

class PaquetesSerializer(serializers.ModelSerializer):
    paq_arrendador = ArrendadorSerializer(read_only=True, source='arrendador')
    paq_arrendatario = InquilinoSerializers(read_only=True, source='arrendatario')
    paq_cotizacion = CotizacionSerializers(read_only=True, source='cotizacion')
    is_staff = serializers.SerializerMethodField()
    
    class Meta:
        model = Paquetes_legales
        fields = '__all__' 
    
    def get_is_staff(self, obj):
        current_user = self.context['request'].user
        
        is_staff_value = current_user.is_staff
        
        if is_staff_value == True:
            #"quiero valida er usuario tambien, queda pendiente para el lunes"
            return is_staff_value
         
        return obj.user.is_staff

class EncuestaSerializer(serializers.ModelSerializer):
    class Meta:
        model = Encuesta
        fields = '__all__'

class Inventario_fotoSerializer(serializers.ModelSerializer):
    class Meta:
        model = Inventario_foto
        fields = '__all__'
        
#FRATERNA
class DRSerializer(serializers.ModelSerializer):
    
    class Meta:
        model = DocumentosResidentes
        fields = '__all__'

class ResidenteSerializers(serializers.ModelSerializer):
    # aval = Fiador_obligadoSerializer(many=True, read_only=True)
    archivos = DRSerializer(many=True, read_only=True)
    user =  User2Serializer(read_only=True)
    
    class Meta:
        model = Residentes
        fields = '__all__'

class ProcesoFraternaSerializers(serializers.ModelSerializer):
    
    class Meta:
        model = ProcesoContrato
        fields = '__all__'
        
class ContratoFraternaSerializer(serializers.ModelSerializer):
    residente_contrato = ResidenteSerializers(read_only=True, source='residente')
    proceso = ProcesoFraternaSerializers(many=True, read_only=True, source ='contrato')
    
    class Meta:
        model = FraternaContratos
        fields = '__all__' 

# Notificaciones
class PostSerializer(serializers.ModelSerializer):    

    class Meta:
        model = Post
        fields = '__all__' 


#FRATERNA SEMILLERO PURISIMA
class DASSerializer(serializers.ModelSerializer):
    
    class Meta:
        model = DocumentosArrendatarios_semilleros
        fields = '__all__'

class Arrentarios_semilleroSerializers(serializers.ModelSerializer):
    archivos = DASSerializer(many=True, read_only=True)
    user =  User2Serializer(read_only=True)
    
    class Meta:
        model = Arrendatarios_semillero
        fields = '__all__'

#Semillero Contratos  
class ProcesoSemilleroSerializers(serializers.ModelSerializer):
    
    class Meta:
        model = ProcesoContrato_semillero
        fields = '__all__'
        
class ContratoSemilleroSerializer(serializers.ModelSerializer):
    arrendatario_contrato = Arrentarios_semilleroSerializers(read_only=True, source='arrendatario')
    proceso = ProcesoSemilleroSerializers(many=True, read_only=True, source ='contrato')
    
    class Meta:
        model = SemilleroContratos
        fields = '__all__' 
        
#FRATERNA GARZA SADA
class DAGSSerializer(serializers.ModelSerializer):
    
    class Meta:
        model = DocumentosArrendatarios_garzasada
        fields = '__all__'

class Arrentarios_GarzaSadaSerializers(serializers.ModelSerializer):
    archivos = DAGSSerializer(many=True, read_only=True)
    user =  User2Serializer(read_only=True)
    
    class Meta:
        model = Arrendatarios_garzasada
        fields = '__all__'

#GarzaSada Contratos  
class ProcesoGarzaSadaSerializers(serializers.ModelSerializer):
    
    class Meta:
        model = ProcesoContrato_garzasada
        fields = '__all__'
        
class ContratoGarzaSadaSerializer(serializers.ModelSerializer):
    arrendatario_contrato = Arrentarios_GarzaSadaSerializers(read_only=True, source='arrendatario')
    proceso = ProcesoGarzaSadaSerializers(many=True, read_only=True, source ='contrato')
    
    class Meta:
        model = GarzaSadaContratos
        fields = '__all__' 
        
class GarzaSadaArrendamientosSerializer(serializers.ModelSerializer):
    # Campos de solo lectura para mostrar información relacionada
    user_info = User2Serializer(read_only=True, source='user')
    arrendatario_contrato = Arrentarios_GarzaSadaSerializers(read_only=True, source='arrendatario')
    proceso_info = ProcesoGarzaSadaSerializers(read_only=True, source='proceso')
    contrato_info = ContratoGarzaSadaSerializer(read_only=True, source='contrato')
    
    class Meta:
        model = DocumentosArrendamientos_garzasada
        fields = '__all__'
        
class IncidenciasGarzaSadaSerializer(serializers.ModelSerializer):
    user_info = User2Serializer(read_only=True, source='user')
    arrendatario_contrato = Arrentarios_GarzaSadaSerializers(read_only=True, source='arrendatario')
    contrato_info = ContratoGarzaSadaSerializer(read_only=True, source='contrato')
    
    class Meta:
        model = IncidenciasGarzaSada
        fields = '__all__'
   
########################### CONTRATOS DASH ########################################
class ContratosDashSerializer(serializers.ModelSerializer):
    #arrendatario_contrato = Arrentarios_semilleroSerializers(read_only=True, source='arrendatario')
    
    
    class Meta:
        model = Contratos
        fields = '__all__' 

class NotificacionSerializer(serializers.ModelSerializer):
    """Serializer para el modelo Notificacion"""
    
    tipo_notificacion_display = serializers.CharField(source='get_tipo_notificacion_display', read_only=True)
    tipo_contrato_display = serializers.CharField(source='get_tipo_contrato_display', read_only=True)
    user_nombre = serializers.CharField(source='user.first_name', read_only=True)
    user_email = serializers.CharField(source='user.email', read_only=True)
    
    # Información del contrato asociado y usuario del contrato
    contrato_info = serializers.SerializerMethodField()
    usuario_contrato_nombre = serializers.SerializerMethodField()
    
    class Meta:
        model = Notificacion
        fields = '__all__'
        read_only_fields = ('fecha_creacion', 'fecha_envio_email', 'fecha_lectura')
    
    def get_usuario_contrato_nombre(self, obj):
        """Obtiene el nombre completo del usuario asociado al contrato"""
        contrato = obj.obtener_contrato()
        if not contrato:
            return None
            
        try:
            if obj.tipo_contrato == 'fraterna':
                # Para contratos fraterna, obtener nombre del residente
                if hasattr(contrato, 'residente') and contrato.residente:
                    return contrato.residente.nombre_completo
            elif obj.tipo_contrato in ['semillero', 'garzasada']:
                # Para semillero y garza sada, obtener nombre del arrendatario
                if hasattr(contrato, 'arrendatario') and contrato.arrendatario:
                    return contrato.arrendatario.nombre_completo
            elif obj.tipo_contrato == 'general':
                # Para contratos generales, obtener nombre del arrendatario
                if hasattr(contrato, 'arrendatario') and contrato.arrendatario:
                    return contrato.arrendatario.nombre_completo
        except Exception as e:
            print(f"Error obteniendo nombre del usuario del contrato: {e}")
            
        return None
    
    def get_contrato_info(self, obj):
        """Obtiene información básica del contrato asociado"""
        contrato = obj.obtener_contrato()
        if not contrato:
            return None
            
        info = {
            'id': contrato.id,
            'tipo': obj.tipo_contrato
        }
        
        try:
            if obj.tipo_contrato == 'fraterna':
                info.update({
                    'inmueble': f"Depto {contrato.no_depa or 'N/A'}",
                    'arrendatario': str(contrato.residente) if contrato.residente else 'N/A',
                    'renta': contrato.renta or 'N/A'
                })
            elif obj.tipo_contrato in ['semillero', 'garzasada']:
                info.update({
                    'inmueble': f"Propiedad {contrato.id}",
                    'arrendatario': str(contrato.arrendatario) if contrato.arrendatario else 'N/A',
                    'renta': getattr(contrato, 'renta', 'N/A')
                })
            elif obj.tipo_contrato == 'general':
                info.update({
                    'inmueble': str(contrato.inmueble) if contrato.inmueble else 'N/A',
                    'arrendatario': str(contrato.arrendatario) if contrato.arrendatario else 'N/A'
                })
        except Exception:
            pass
        
        return info

# ===================== Reservas Asador =====================
class ReservaAsadorSerializer(serializers.ModelSerializer):
    class Meta:
        model = ReservaAsador
        fields = '__all__'