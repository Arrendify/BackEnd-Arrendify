from rest_framework import serializers
from ..home.models import *
from ..authentication.models import *
from ..authentication.serializers import User2Serializer
from .models import Notification
from ..accounts.models import *
from django.conf import settings

class DFSerializer(serializers.ModelSerializer):
     
    class Meta:
        model = DocumentosFiador
        fields = '__all__'
class DISerializer(serializers.ModelSerializer):
    inquilinos_nombre = serializers.CharField(source='arrendatario.nombre_completo', read_only=True)
    class Meta:
        model = DocumentosInquilino
        fields = '__all__'

class AvalSerializer(serializers.ModelSerializer):
    inquilino_nombre = serializers.CharField(source='arrendatario.nombre_completo', read_only=True)
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
    nombre_empresa= serializers.CharField(source='arrendador.nombre_empresa', read_only=True)
    nombre_completo= serializers.CharField(source='arrendador.nombre_completo', read_only=True)
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
class InvestigacionLaboralSerializer(serializers.ModelSerializer):
    # Definir campos que esperamos recibir, incluidas las referencias a los archivos.
    
    # Si tienes archivos, puedes usar FileField o ImageField según el tipo de archivo
    cartalab_inv1 = serializers.FileField(required=False)
    cartalab_inv2 = serializers.FileField(required=False)
    cartalab_inv3 = serializers.FileField(required=False)
    cartalab_inv4 = serializers.FileField(required=False)
    
    class Meta:
        model = Investigacion_Laboral
        fields = '__all__'

class InvestigacionJudicialSerializer(serializers.ModelSerializer):
    
    class Meta:
        model = Investigacion_Judicial
        fields ='__all__'
class InvestigacionFinancieraSerializer(serializers.ModelSerializer):
    
    class Meta:
        model = Investigacion_Financiera
        fields ='__all__'
        
class InvestigacionInquilinoSerializer(serializers.ModelSerializer):

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

class NotificationSerializer(serializers.ModelSerializer):
    actor_name = serializers.CharField(source='actor', read_only=True) # con este metodo obtengo los nombres en lugar del id con *source*
    destiny_name = serializers.CharField(source='destiny', read_only=True)
    

    class Meta:
        model = Notification
        fields = '__all__'  # O especifica los campos que deseas serializar, por ejemplo: ['field1', 'field2']

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
   
########################### CONTRATOS DASH ########################################
class ContratosDashSerializer(serializers.ModelSerializer):
    #arrendatario_contrato = Arrentarios_semilleroSerializers(read_only=True, source='arrendatario')
    
    
    class Meta:
        model = Contratos
        fields = '__all__' 