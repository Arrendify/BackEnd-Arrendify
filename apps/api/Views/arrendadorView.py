from rest_framework.response import Response
from rest_framework import viewsets
from rest_framework.authentication import TokenAuthentication,SessionAuthentication
from ...home.models import *
from ..serializers import *
from rest_framework.decorators import action


from rest_framework.response import Response

#intento de factorizacion 1

from rest_framework import status
from rest_framework.exceptions import ValidationError
from rest_framework import viewsets


from rest_framework.authentication import TokenAuthentication,SessionAuthentication
from rest_framework.permissions import IsAuthenticated

from rest_framework.decorators import action

#nuevo mod user
from ...accounts.models import CustomUser
User = CustomUser

# metodos s3
from ..views import eliminar_archivo_s3

#correo
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.base import MIMEBase
from email import encoders
from smtplib import SMTPException
from decouple import config

#obtener Logs de errores
import logging
import sys
logger = logging.getLogger(__name__)

from rest_framework.authentication import TokenAuthentication

# ----------------------------------Metodos Extras----------------------------------------------- #
# ----------------------------------Metodo para disparar notificaciones de manera individual----------------------------------------------- #
def send_noti_legal(self, request, *args, **kwargs):
        print("entramos al metodo de notificaiones independientes")
        print("lo que llega es en self",self)
        print("lo que llega es en kwargs",kwargs["title"])
        print("lo que llega es en kwargs",kwargs['text'])
        print("lo que llega es en kwargs",kwargs['url'])
        
        print("request: ",request.data)
        print("")
        actor = User.objects.all().filter(username = 'Legal').first()
        print("request verbo",kwargs["title"])
        
        try:
            print("entramos en el tri")
            user_session = request.user
            print("el que envia usuario es: ", user_session)
            print("el que recibe actor es: ",actor)
          
            data_noti = {'title':kwargs["title"], 'text':kwargs["text"], 'user':user_session.id, 'url':kwargs['url']}
          
            print("Post serializer a continuacion")
            post_serializer = PostSerializer(data=data_noti) #Usa el serializer_class
            if post_serializer.is_valid(raise_exception=True):
                print("hola es valido el serializer")
                datos = post_serializer.save(user = actor)
                print('datos',datos)
                return Response({'Post': post_serializer.data}, status=status.HTTP_201_CREATED)
            
            else:
                print("Error en validacion", post_serializer.errors)
                return Response({'errors': post_serializer.errors})
            
        except Exception as e:
            print("error",e)
            return Response({'error': str(e)}, status=status.HTTP_400_BAD_REQUEST)

def send_noti_comentario(self, request, *args, **kwargs):
        print("entramos al metodo de notificaiones independientes")
        print("lo que llega es en self",self)
        print("lo que llega es en kwargs",kwargs)
     

        print("lo que llega es en kwargs")
        print("Tittle",kwargs["title"])
        print("Text",kwargs['text'])
        print("URL",kwargs['url'])
        print("")
        
        print("request data que llega en noti: ",request)
        print("mi target es el usuario de los documentos ",request.arrendador.user.id)
        print("request data que llega en noti dcit: ",request.__dict__)
 
        print("")
        #sleccionamos al actor que es el que va a recivir el comentario
        actor = User.objects.all().filter(id = request.arrendador.user.id).first()
        print("request verbo",kwargs["title"])
        
        try:
            print("entramos en el tri")
            user_session = request.user
            print("el que envia usuario es: ", user_session)
            print("el que recibe actor es: ",actor)
          
            data_noti = {'title':kwargs["title"], 'text':kwargs["text"], 'user':user_session.id, 'url':kwargs['url']}
          
            print("Post serializer a continuacion")
            post_serializer = PostSerializer(data=data_noti) #Usa el serializer_class
            if post_serializer.is_valid(raise_exception=True):
                print("hola es valido el serializer")
                datos = post_serializer.save(user = actor)
                print('datos',datos)
                return Response({'Post': post_serializer.data}, status=status.HTTP_201_CREATED)
            
            else:
                print("Error en validacion", post_serializer.errors)
                return Response({'errors': post_serializer.errors})
            
        except Exception as e:
            print("error",e)
            return Response({'error': str(e)}, status=status.HTTP_400_BAD_REQUEST)

class ArrendadorViewSet(viewsets.ModelViewSet):
    authentication_classes = [TokenAuthentication, SessionAuthentication]
    lookup_field = 'slug'
    queryset = Propietario.objects.all()
    serializer_class = ArrendadorSerializer
    serializer_class_archivos = DocumentosArrendadorSerializer
        
    def list(self, request):
        user_session = self.request.user
        try:
            if user_session.is_staff:
                # Crear una copia de los datos serializados
                print("soy staff en arrendador")
                snippets = Propietario.objects.all().order_by('-id')
                serializer = ArrendadorSerializer(snippets, many=True)
                serialized_data = serializer.data
              
               
                # Agregar el campo 'is_staff'
                for item in serialized_data:
                    item['is_staff'] = True

                print(snippets)            
                # Devolver la respuesta
                return Response(serialized_data)
            
            elif user_session.rol == "Inmobiliaria":  
                #tengo que buscar a los arrendadores que tiene a un agente vinculado
                print("soy inmobiliaria", user_session.name_inmobiliaria)
                agentes = User.objects.all().filter(pertenece_a = user_session.name_inmobiliaria) 
                
                #busqueda de arrendadores propios y registrados por mis agentes
                arrendadores_a_cargo = Arrendador.objects.filter(user_id__in = agentes)
                arrendadores_mios = Arrendador.objects.filter(user_id = user_session)
                mios = arrendadores_a_cargo.union(arrendadores_mios)
                
                #busqueda de inquilino vinculado
                pertenece2 = Arrendador.objects.filter(mi_agente_es__icontains = agentes.values("first_name"))
                pertenece = Arrendador.objects.filter(mi_agente_es__in = agentes.values("first_name"))
                pertenece = pertenece.union(pertenece2)
                arrendador_all = mios.union(pertenece).order_by('-id')
               
                print("Registrados por mi o por un agente directo", mios)
                print("Independientes vinculado(s) a un agente(s)", pertenece)
                print("Todos los arrendadores",arrendador_all)
               # print("inquilinos_all con ids",arrendador_all("id"))
                
                serializer = ArrendadorSerializer(arrendador_all, many=True)
                serialized_data = serializer.data
                
                if not serialized_data:
                    print("no hay datos mi carnal")
                    return Response({"message": "No hay datos disponibles",'asunto' :'1'})
                
                # Agregar el campo 'is_staff'
                for item in serialized_data:
                    item['inmobiliaria'] = True
                    
                return Response(serialized_data)      
        
            elif user_session.rol == "Agente":  
                print("soy agente", user_session.first_name)
                agente_qs = Arrendador.objects.filter(user_id = user_session)
                print(agente_qs)
                pertenece = Arrendador.objects.filter(mi_agente_es__icontains = user_session.first_name)
                print(pertenece)
                arredores_a_cargo = agente_qs.union(pertenece).order_by('-id')
                serializer = ArrendadorSerializer(arredores_a_cargo, many=True)
                serialized_data = serializer.data
                
                if not serialized_data:
                    print("no hay datos mi carnal")
                    return Response({"message": "No hay datos disponibles",'asunto' :'2'})
                
                for item in serialized_data:
                    item['agente'] = True
            
                return Response(serialized_data)
     
            else:
                # Listar muchos a muchos
                # optimizar esto
                # Obtener todos los inquilinos del usuario actual
                arrendadores_propios = Propietario.objects.all().filter(user_id = user_session)
                
                # Obtener todos los arrendadores amigos del usuario actual
                #inquilinos_amigos = Arrendatario.objects.all().filter(user_id = user_session)
            
                # Obtener inquilinos ligados a los arrendadores amigos
                #arrendador_amigos = Propietario.objects.all().filter(amigo_arrendador__sender__in = inquilinos_amigos)
            
                # Combinar inquilinos propios e inquilinos amigos sin duplicados basados en el ID
                #snippets = arrendadores_propios.union(arrendador_amigos).order_by('-id')
                serializer = ArrendadorSerializer(arrendadores_propios, many=True)
                serialized_data = serializer.data
                return Response(serialized_data)
                
        except Exception as e:
            print(f"el error es: {e}")
            exc_type, exc_obj, exc_tb = sys.exc_info()
            logger.error(f"{datetime.now()} Ocurrió un error en el archivo {exc_tb.tb_frame.f_code.co_filename}, en el método {exc_tb.tb_frame.f_code.co_name}, en la línea {exc_tb.tb_lineno}:  {e}")
            return Response({'error': str(e)}, status=status.HTTP_400_BAD_REQUEST)

    def create(self, request, *args, **kwargs):
        user_session = self.request.user
        try:
            print("Llegando a create arrendador")
            # request.data['user'] = request.user.id
            regimen = request.data['regimen_fiscal']
            print(regimen)
            if regimen == "Persona Moral":
                data = request.data
                data['email'] = "na@na.com"
                
            arrendador_serializer = self.get_serializer(data=request.data) # Usa el serializer_class
            if arrendador_serializer.is_valid(raise_exception=True):
                arrendador_serializer.save(user = user_session)
                print("Guardado arrendador")

                return Response({'arrendador': arrendador_serializer.data}, status=status.HTTP_201_CREATED)
            else:
                print("Error al crear arrendador")
                return Response({'error': arrendador_serializer.errors},status = status.HTTP_400_BAD_REQUEST)
        except ValidationError as e:
            print(f"error de validacion: {e.detail}")
            print(dir(e))
            dic = dict(e.detail)
            primer_valor = next(iter(dic.values()))
            error = f"Email Invalido : {primer_valor}"

            exc_type, exc_obj, exc_tb = sys.exc_info()
            logger.error(
                f"{datetime.now()} Ocurrió un error en el archivo {exc_tb.tb_frame.f_code.co_filename}, "
                f"en el método {exc_tb.tb_frame.f_code.co_name}, "
                f"en la línea {exc_tb.tb_lineno}: {e}"
            )
            return Response({'error_try': error}, status=status.HTTP_400_BAD_REQUEST)
        except Exception as e:
            print(f"el error es: {e}")
            exc_type, exc_obj, exc_tb = sys.exc_info()
            logger.error(f"{datetime.now()} Ocurrió un error en el archivo {exc_tb.tb_frame.f_code.co_filename}, en el método {exc_tb.tb_frame.f_code.co_name}, en la línea {exc_tb.tb_lineno}:  {e}")
            return Response({'error_exept': str(e)}, status = status.HTTP_302_FOUND)
        
    
    def retrieve(self, request, slug=None, *args, **kwargs):
        try:
            print("Entrando a retrieve")
            modelos = self.queryset #Toma los datos de Inmuebles.objects.all() que esta al inicio de la clase viewset
            arrendador = modelos.filter(slug=slug)
            if arrendador:
                arrendador_serializer = self.serializer_class(arrendador, many=True)
                # Agregar el campo 'is_staff'
                serialized_data = arrendador_serializer.data
                for item in serialized_data:
                    item['is_staff'] = True
                return Response(serialized_data, status=status.HTTP_200_OK)
            else:
                return Response({'message': 'No hay persona con esos datos'}, status = status.HTTP_400_BAD_REQUEST)
        except Exception as e:
            return Response({'error': str(e)}, status=status.HTTP_400_BAD_REQUEST)
    
    def update(self, request, *args, **kwargs):
        try:
            instance = self.get_object()
            serializer = self.get_serializer(instance, data=request.data, partial=True)
            serializer.is_valid(raise_exception=True)
            self.perform_update(serializer)
            print("edito arrendador ")
            return Response(serializer.data, status=status.HTTP_200_OK)
        except ValidationError as e:
            return Response({'errors': e.detail}, status=status.HTTP_400_BAD_REQUEST)
        except Exception as e:
            print(f"el error es: {e}")
            exc_type, exc_obj, exc_tb = sys.exc_info()
            logger.error(f"{datetime.now()} Ocurrió un error en el archivo {exc_tb.tb_frame.f_code.co_filename}, en el método {exc_tb.tb_frame.f_code.co_name}, en la línea {exc_tb.tb_lineno}:  {e}")
            return Response({'error': str(e)}, status=status.HTTP_400_BAD_REQUEST)
            
    def destroy (self,request, *args, **kwargs):
        try:
            print("Esta entrando a eliminar")
            arrendador = self.get_object()
            if arrendador:
                arrendador.delete()
                return Response({'message': 'Arrendador eliminado'}, status=204)
            return Response({'message': 'Error al eliminar'}, status=400)
        except Exception as e:
            return Response({'error': str(e)}, status=status.HTTP_400_BAD_REQUEST)
            
  
class Documentos_Arrendador(viewsets.ModelViewSet):
    authentication_classes = [TokenAuthentication, SessionAuthentication]
    permission_classes = [IsAuthenticated]
    
    queryset = DocumentosArrendador.objects.all()
    serializer_class = DocumentosArrendadorSerializer
   
    def list(self, request, *args, **kwargs):
        try:
          
            queryset = self.filter_queryset(self.get_queryset())
            Serializers = self.get_serializer(queryset, many=True)
            return Response(Serializers.data ,status=status.HTTP_200_OK)
        
        except Exception as e:
            print(f"el error es: {e}")
            exc_type, exc_obj, exc_tb = sys.exc_info()
            logger.error(f"{datetime.now()} Ocurrió un error en el archivo {exc_tb.tb_frame.f_code.co_filename}, en el método {exc_tb.tb_frame.f_code.co_name}, en la línea {exc_tb.tb_lineno}:  {e}")
            return Response({'error': str(e)}, status= status.HTTP_400_BAD_REQUEST)
    
    def create (self, request, *args,**kwargs):
        try: 
            data = request.data
            print(data)
            print("Id_arrendador",  request.data.get('arrendador'))
            
            documentos = ['ine', 'acta_constitutiva', 'extras']
            for field in documentos:
                if field in request.FILES:
                    data[field] = request.FILES[field]
                else:
                    data[field] = None

            data['user'] = request.user.id
            data['arrendador'] = request.data.get('arrendador')
            print("soy data", data)

            if data:
                print("entre al if de data")
                documentos_serializer = self.serializer_class(data=data)
                print()
                if documentos_serializer.is_valid():
                    documentos_serializer.save()
                else:
                    print("Serializer no es valido")
                    return Response(documentos_serializer.error, status=400)
                return Response(documentos_serializer.data, status=status.HTTP_201_CREATED)
            else:
                return Response({'error': 'No file provided'}, status=status.HTTP_400_BAD_REQUEST)
            
        except Exception as e:
            print(f"el error es: {e}")
            exc_type, exc_obj, exc_tb = sys.exc_info()
            logger.error(f"{datetime.now()} Ocurrió un error en el archivo {exc_tb.tb_frame.f_code.co_filename}, en el método {exc_tb.tb_frame.f_code.co_name}, en la línea {exc_tb.tb_lineno}:  {e}")
            return Response({'error': str(e)}, status=status.HTTP_200_OK)                

    def destroy(self, request, pk=None, *args, **kwargs):
        try:
            documentos_inquilinos = self.get_object()
            documento_inquilino_serializer = self.serializer_class(documentos_inquilinos)
            print("Soy ine", documento_inquilino_serializer.data['ine'])
            print("1")
            if documentos_inquilinos:
                ine = documento_inquilino_serializer.data['ine']
                print("Soy ine 2", ine)
                comp_dom= documento_inquilino_serializer.data['comp_dom']
                rfc= documento_inquilino_serializer.data['escrituras_titulo']
                print("Soy RFC", rfc)
                ruta_ine = 'apps/static'+ ine
                print("Ruta ine", ruta_ine)
                ruta_comprobante_domicilio = 'apps/static'+ comp_dom
                ruta_rfc = 'apps/static'+ rfc
                print("Ruta com", ruta_comprobante_domicilio)
                print("Ruta RFC", ruta_rfc)
            
                # self.perform_destroy(documentos_arrendador)  #Tambien se puede eliminar asi
                documentos_inquilinos.delete()
                return Response({'message': 'Archivo eliminado correctamente'}, status=204)
            else:
                return Response({'message': 'Error al eliminar archivo'}, status=400)
        except Exception as e:
            print(f"el error es: {e}")
            exc_type, exc_obj, exc_tb = sys.exc_info()
            logger.error(f"{datetime.now()} Ocurrió un error en el archivo {exc_tb.tb_frame.f_code.co_filename}, en el método {exc_tb.tb_frame.f_code.co_name}, en la línea {exc_tb.tb_lineno}:  {e}")
            return Response({'error': str(e)}, status= status.HTTP_400_BAD_REQUEST)
        
        
    def retrieve(self, request, pk=None):
        try:
            documentos = self.queryset #Toma los datos de Inmuebles.objects.all() que esta al inicio de la clase viewset
            inquilino = documentos.filter(id=pk)
            serializer_inquilino = DISerializer(inquilino, many=True)
            print(serializer_inquilino.data)
            ine = serializer_inquilino.data[0]['ine']
            print(ine)
            # documentos_arrendador = self.get_object()
            # print(documentos_arrendador)
            return Response(serializer_inquilino.data)
        except Exception as e:
            print(f"el error es: {e}")
            exc_type, exc_obj, exc_tb = sys.exc_info()
            logger.error(f"{datetime.now()} Ocurrió un error en el archivo {exc_tb.tb_frame.f_code.co_filename}, en el método {exc_tb.tb_frame.f_code.co_name}, en la línea {exc_tb.tb_lineno}:  {e}")
            return Response({'error': str(e)}, status= status.HTTP_400_BAD_REQUEST)
    
   
    def update(self, request, *args, **kwargs):
        try:
            instance = self.get_object()
            serializer = self.get_serializer(instance, data=request.data, partial=True)
            serializer.is_valid(raise_exception=True)
            print(request.data)
            
            # Verificar si se proporciona un nuevo archivo adjunto
            if 'ine' in request.data:
                print("arremdador pf")
                ine = request.data['ine']
                archivo = instance.ine
                eliminar_archivo_s3(archivo)
                instance.ine = ine  # Actualizar el archivo adjunto sin eliminar el anterior
            
            if 'acta_constitutiva' in request.data:
                print("arrendador pm")
                acta_constitutiva = request.data['acta_constitutiva']
                archivo = instance.acta_constitutiva
                eliminar_archivo_s3(archivo)
                instance.acta_constitutiva = acta_constitutiva  # Actualizar el archivo adjunto sin eliminar el anterior
            
            if 'extras' in request.data:
                extras = request.data['extras']
                archivo = instance.extras
                eliminar_archivo_s3(archivo)
                instance.extras = extras  # Actualizar el archivo adjunto sin eliminar el anterior   
        
            print("notificacion a legal de que actualizaron documentos")   
            if instance.arrendador.regimen_fiscal == "Persona Moral":             
                send_noti_legal(DocumentosArrendador, request, title="Actualización documentos", text=f"El Arrendador: {instance.arrendador.nombre_empresa} ah actualizado documentos", url = f"arrendadores/#{instance.arrendador.slug}")
            else:    
                send_noti_legal(DocumentosArrendador, request, title="Actualización documentos", text=f"El Arrendador: {instance.arrendador.nombre_completo} ah actualizado documentos", url = f"arrendadores/#{instance.arrendador.slug}")
            
        
            serializer.update(instance, serializer.validated_data)
            print(serializer.data['ine'])# Actualizar el archivo adjunto sin eliminar el anterior
            #print(serializer)# Actualizar el archivo adjunto sin eliminar el anterior
            print("Documentos actualizados")
            return Response(serializer.data)

        
        except Exception as e:
            print(f"el error es: {e}")
            exc_type, exc_obj, exc_tb = sys.exc_info()
            logger.error(f"{datetime.now()} Ocurrió un error en el archivo {exc_tb.tb_frame.f_code.co_filename}, en el método {exc_tb.tb_frame.f_code.co_name}, en la línea {exc_tb.tb_lineno}:  {e}")
            return Response({'error': str(e)}, status= status.HTTP_400_BAD_REQUEST)
    
    #Utilizamos el decorador @action(detail=True, methods=['put']) para definir esta acción como una operación de tipo PUT sobre un recurso específico (detail=True) lo que replica el metodo update del viewset.
    # y para usarlo pones el metodo despues del id que vas a utilizar ej. /arrendadores_documentos/id/update_comentarios/
    @action(detail=True, methods=['put'])    
    def update_comentarios(self, request, *args, **kwargs):
        try:
            instance = self.get_object()
            serializer = self.get_serializer(instance, data=request.data, partial=True)
            serializer.is_valid(raise_exception=True)
            print(request.data)
            
            if request.data.get('comentarios_ine') or request.data.get('comentarios_acta_constitutiva') or request.data.get('comentarios_extras'):
                print("tengo datos comentarios")
                if instance.arrendador.regimen_fiscal == "Persona Moral":
                    send_noti_comentario(Arrendador, instance, title="Tienes un comentario en docs", text=f"El Equipo legal ah agregado un comentario en los docs del arrendador: {instance.arrendador.nombre_empresa}", url = f"arrendadores/#{instance.arrendador.slug}")
                    
                else:
                    send_noti_comentario(Arrendador, instance, title="Tienes un comentario en docs", text=f"El Equipo legal ah agregado un comentario en los docs del arrendador: {instance.arrendador.nombre_completo}", url = f"arrendadores/#{instance.arrendador.slug}")

            else:
                print("borramos comentarios")
            

            serializer.update(instance, serializer.validated_data)
           
            print("Comentarios actualizados")
            return Response(serializer.data)

        
        except Exception as e:
            print(f"el error es: {e}")
            exc_type, exc_obj, exc_tb = sys.exc_info()
            logger.error(f"{datetime.now()} Ocurrió un error en el archivo {exc_tb.tb_frame.f_code.co_filename}, en el método {exc_tb.tb_frame.f_code.co_name}, en la línea {exc_tb.tb_lineno}:  {e}")
            return Response({'error': str(e)}, status= status.HTTP_400_BAD_REQUEST)
    

