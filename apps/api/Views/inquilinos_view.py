#DRF
from rest_framework.decorators import api_view
from rest_framework.response import Response
from rest_framework import viewsets
from rest_framework import status
from rest_framework.authentication import TokenAuthentication,SessionAuthentication
from rest_framework.permissions import IsAuthenticated, AllowAny

#modelos
from ...home.models import Inquilino
from ..serializers import *
from ...accounts.models import CustomUser
User = CustomUser


# metodos s3
from ..views import eliminar_archivo_s3
#obtener Logs de errores
import logging
import sys
logger = logging.getLogger(__name__)

# ----------------------------------Metodo para disparar notificaciones de manera individual----------------------------------------------- #
def send_noti(self, request, *args, **kwargs):
        print("entramos al metodo de notificaiones independientes")
        print("lo que llega es en self",self)
        print("lo que llega es en kwargs",kwargs["title"])
        print("lo que llega es en kwargs",kwargs['text'])
        print("lo que llega es en kwargs",kwargs['url'])
        
        print("request: ",request.data)
        print("")
        actor = User.objects.all().filter(username = 'Arrendatario1').first()
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
            exc_type, exc_obj, exc_tb = sys.exc_info()
            logger.error(f"{datetime.now()} Ocurrió un error en el archivo {exc_tb.tb_frame.f_code.co_filename}, en el método {exc_tb.tb_frame.f_code.co_name}, en la línea {exc_tb.tb_lineno}: {e}")
            return Response({'error': str(e)}, status=status.HTTP_400_BAD_REQUEST)

# ----------------------------------Metodo para disparar notificaciones a varios destinos----------------------------------------------- #
def send_noti_varios(self, request, *args, **kwargs):
        print("entramos al metodo de notificaiones independientes")
        print("lo que llega es en self",self)
        print("lo que llega es en kwargs",kwargs["title"])
        print("lo que llega es en kwargs",kwargs['text'])
        print("lo que llega es en kwargs",kwargs['url'])
        print("request: ",request.data)
        print("")
        
        print("request verbo",kwargs["title"])
        try:
            print("entramos en el try")
            user_session = request.user
            print("el que envia usuario es: ", user_session)
            
            destinatarios = User.objects.all().filter(pertenece_a = 'Arrendify')
            
            print("actores:",destinatarios)
            
            data_noti = {'title':kwargs["title"], 'text':kwargs["text"], 'user':user_session.id, 'url':kwargs['url']}
            print("Post serializer a continuacion")
        
            for destiny in destinatarios:
                post_serializer = PostSerializer(data=data_noti) #Usa el serializer_class
                if post_serializer.is_valid(raise_exception=True):
                    print("hola")
                    print("destinyes",destiny)
                    datos = post_serializer.save(user = destiny)
                    print("Guardado residente")
                    print('datos',datos)
                else:
                    print("Error en validacion",post_serializer.errors)
            return Response({'Post': post_serializer.data}, status=status.HTTP_201_CREATED)
            
        except Exception as e:
            exc_type, exc_obj, exc_tb = sys.exc_info()
            logger.error(f"{datetime.now()} Ocurrió un error en el archivo {exc_tb.tb_frame.f_code.co_filename}, en el método {exc_tb.tb_frame.f_code.co_name}, en la línea {exc_tb.tb_lineno}: {e}")
            return Response({'error': str(e)}, status=status.HTTP_400_BAD_REQUEST)


class inquilinosViewSet(viewsets.ModelViewSet):
    authentication_classes = [TokenAuthentication, SessionAuthentication]
    permission_classes = [IsAuthenticated]
    serializer_class = InquilinoSerializers
    queryset = Arrendatario.objects.all()
    
    def list(self, request, *args, **kwargs):
        user_session = request.user
        try:    
            if request.method == 'GET':
                if user_session.is_staff:
                    snippets = Arrendatario.objects.all().order_by('-id')
                    
                    # Crear una copia de los datos serializados
                    serializer = InquilinoSerializers(snippets, many=True)
                    serialized_data = serializer.data

                    # Agregar el campo 'is_staff'
                    for item in serialized_data:
                        item['is_staff'] = True

                    # Devolver la respuesta
                    return Response(serialized_data)
                
                elif user_session.rol == "Inmobiliaria":  
                    #tengo que busca a los inquilinos que tiene a un agente vinculado
                    print("soy inmobiliaria", user_session.name_inmobiliaria)
                    agentes = User.objects.all().filter(pertenece_a = user_session.name_inmobiliaria) 
                    
                    #busqueda de inquilino propios y registrados por mis agentes
                    inquilinos_a_cargo = Arrendatario.objects.filter(user_id__in = agentes)
                    inquilinos_mios = Arrendatario.objects.filter(user_id = user_session)
                    print("mis registros propios como inmobiliaria",inquilinos_mios)
                    mios = inquilinos_a_cargo.union(inquilinos_mios)
                    
                    #busqueda de inquilino vinculado
                    # pertenece2 = Arrendatario.objects.filter(mi_agente_es__icontains = agentes.values("first_name"))
                    # pertenece = Arrendatario.objects.filter(mi_agente_es__in = agentes.values("first_name"))
                    # pertenece = pertenece.union(pertenece2)
                    
                    #inquilinos_all = mios.union(pertenece)
                    #print("inquilinos a cargo", inquilinos_a_cargo.values())
                    # print("Registrados por mi o por un agente directo", mios)
                    # print("Independientes vinculado(s) a un agente(s)", pertenece)
                    # print("inquilinos_all",inquilinos_all)
                    
                    
                    serializer = InquilinoSerializers(mios, many=True)
                    serialized_data = serializer.data
                    
                    if not serialized_data:
                        print("no hay datos mi carnal")
                        return Response({"message": "No hay datos disponibles",'asunto' :'1'})
                    
                    # Agregar el campo 'is_staff'
                    for item in serialized_data:
                        item['inmobiliaria'] = True
                        
                    return Response(serialized_data)      
                
                elif user_session.rol == "Agente":  
                    print("soy Agente", user_session.first_name)
                    #obtengo mis inquilinos
                    inquilinos_ag = Arrendatario.objects.filter(user_id = user_session)
                    #obtengo mis inquilinos vinculados
                    #pertenece = Arrendatario.objects.filter(mi_agente_es__icontains = user_session.first_name)
                    # pertenece = Arrendatario.objects.filter(mi_agente_es = user_session.first_name)
                    # pertenece = Arrendatario.objects.filter(mi_agente_es__in = user_session.first_name)
                    # pertenece = pertenece.union(pertenece2)
                    #inquilinos_all = inquilinos_ag.union(pertenece)
                    serializer = InquilinoSerializers(inquilinos_ag, many=True)
                    serialized_data = serializer.data
                    
                    if not serialized_data:
                        print("no hay datos mi carnal")
                        return Response({"message": "No hay datos disponibles",'asunto' :'2'})

                    for item in serialized_data:
                        item['agente'] = True
                        
                    return Response(serialized_data)         
                
                else:
                    # Listar muchos a muchos
                    # Obtener todos los inquilinos del usuario actual
                    inquilinos_propios = Arrendatario.objects.all().filter(user_id = user_session)
                    print(inquilinos_propios)
                    
                    # Obtener todos los arrendadores amigos del usuario actual
                    arrendadores_amigos = Propietario.objects.all().filter(user_id = user_session)
                    print(arrendadores_amigos)
                    # Obtener inquilinos ligados a los arrendadores amigos
                    #inquilinos_amigos = Arrendatario.objects.filter(amigo_inquilino__receiver__in = arrendadores_amigos)
                    #print(inquilinos_amigos)
                    # Combinar inquilinos propios e inquilinos amigos sin duplicados basados en el ID
                    #snippets = inquilinos_propios.union(inquilinos_amigos)
                    
                    
                    
                    serializer = InquilinoSerializers(inquilinos_propios, many=True)
            
                    return Response(serializer.data)
        except Exception as e:
            print(f"el error es: {e}")
            exc_type, exc_obj, exc_tb = sys.exc_info()
            logger.error(f"{datetime.now()} Ocurrió un error en el archivo {exc_tb.tb_frame.f_code.co_filename}, en el método {exc_tb.tb_frame.f_code.co_name}, en la línea {exc_tb.tb_lineno}:  {e}")
            return Response({'error': str(e)}, status=status.HTTP_400_BAD_REQUEST)

    def create(self, request, *args, **kwargs):
                user_session = request.user
                try:
                    regimen_fiscal = request.data.get("regimen_fiscal")
                    logger.debug("llega a regimen")
                    logger.debug(f"Este es el Regimen: {regimen_fiscal}")
                    print("Este es el Regimen: ", regimen_fiscal)
                    
                    data = request.data.copy()
                    if regimen_fiscal == "Persona Moral":
                        data['email'] = "na@na.com"
                    
                    serializer = InquilinoSerializers(data=data)
                    if serializer.is_valid():
                        logger.debug("Guardo Inquilino")
                        print("Guardo Inquilino")
                        serializer.save(user=user_session)
                        return Response(serializer.data, status=status.HTTP_201_CREATED)
                    else:
                        logger.error(f"Error en el serializer de inquilino: {serializer.errors}")
                        print("No Guardo Inquilino", serializer.errors)
                        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
                except Exception as e:
                    exc_type, exc_obj, exc_tb = sys.exc_info()
                    logger.error(f"{datetime.now()} Ocurrió un error en el archivo {exc_tb.tb_frame.f_code.co_filename}, en el método {exc_tb.tb_frame.f_code.co_name}, en la línea {exc_tb.tb_lineno}: {e}")
                    return Response({'error': str(e)}, status=status.HTTP_400_BAD_REQUEST)


    def update(self, request, *args, **kwargs):
            try:
                print("Yo soy request", request.data)
                instace = self.get_object()
                print("Nombre del Inquilino:", instace)
                InquilinoSerializers = self.get_serializer(instace, data=request.data, partial = True)
                InquilinoSerializers.is_valid(raise_exception=True)
                self.perform_update(InquilinoSerializers)
                print("Guardo Inquilino")
                
                #send_noti(inquilino, request, title="Actualizacion de Inquilino", text=f"El Inquilino: {inquilino.nombre} {inquilino.apellido} ah sido actualizado por {request.user}", url = f"inquilinos/#{inquilino.nombre}_{inquilino.apellido}_{inquilino.apellido1}")
                #send_noti_varios(inquilino, request, title="Actualizacion de Inquilino", text=f"El Inquilino: {inquilino.nombre_completo} ah sido actualizado por {request.user}", url = f"inquilinos/#{inquilino.nombre_completo}")
                print("despues de metodo send_noti")
                return Response(InquilinoSerializers.data, status=status.HTTP_200_OK)
                
                print("No guardo Inquilino")
            except Exception as e: 
                exc_type, exc_obj, exc_tb = sys.exc_info()
                logger.error(f"{datetime.now()} Ocurrió un error en el archivo {exc_tb.tb_frame.f_code.co_filename}, en el método {exc_tb.tb_frame.f_code.co_name}, en la línea {exc_tb.tb_lineno}: {e}")
                return Response({'error': str(e)}, status=status.HTTP_400_BAD_REQUEST)



    def destroy(self, request, *args, **kwargs):
        try:
            id = request.data.get('id')
            print("Valor de la id", id)
            inquilino = Inquilino.objects.get(id=id)
            inquilino.delete()
            print("Elimino Inquilino")
            return Response(status=status.HTTP_200_OK)
        except Exception as e:
            exc_type, exc_obj, exc_tb = sys.exc_info()
            logger.error(f"{datetime.now()} Ocurrió un error en el archivo {exc_tb.tb_frame.f_code.co_filename}, en el método {exc_tb.tb_frame.f_code.co_name}, en la línea {exc_tb.tb_lineno}:  {e}")
            print("No elimino Inquilino")
            return Response({'error': str(e)}, status=status.HTTP_400_BAD_REQUEST)


class DocumentosInquilinoViewSet(viewsets.ModelViewSet):
    authentication_classes = [TokenAuthentication, SessionAuthentication]
    permission_classes = [IsAuthenticated]
    
    queryset = DocumentosInquilino.objects.all()
    serializer_class = DISerializer
   
    def list(self, request, *args, **kwargs):
        content = {
            'user': str(request.user),
            'auth': str(request.auth),
        }
        queryset = self.filter_queryset(self.get_queryset())
        InquilinoSerializers = self.get_serializer(queryset, many=True)
       
        return Response(InquilinoSerializers.data ,status=status.HTTP_200_OK)
    
    def create (self, request, *args,**kwargs):
        
        user_session = str(request.user.id)
   
        try: 
            data = request.data
         
            data = {
                    "Ine": request.FILES.get('Ine', None),
                    "Comp_dom": request.FILES.get('Comp_dom', None),
                    "Rfc": request.FILES.get('Rfc', None),
                    "Ingresos": request.FILES.get('Ingresos', None),
                    "Extras": request.FILES.get('Extras', None),
                    "Recomendacion_laboral": request.FILES.get('Recomendacion_laboral', None),
                    "Acta_constitutiva":request.data['Acta_constitutiva'],
                    "arrendatario":request.data['arrendatario'],
                    "user":user_session
                }
          
            if data:
                documentos_serializer = self.get_serializer(data=data)
                documentos_serializer.is_valid(raise_exception=True)
                documentos_serializer.save()
                return Response(documentos_serializer.data, status=status.HTTP_201_CREATED)
            else:
                return Response({'error': 'No file provided'}, status=status.HTTP_400_BAD_REQUEST)
        except Exception as e:
            exc_type, exc_obj, exc_tb = sys.exc_info()
            logger.error(f"{datetime.now()} Ocurrió un error en el archivo {exc_tb.tb_frame.f_code.co_filename}, en el método {exc_tb.tb_frame.f_code.co_name}, en la línea {exc_tb.tb_lineno}: {e}")
            return Response({'error': str(e)}, status=status.HTTP_400_BAD_REQUEST)
        

    
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
            return Response({'error': str(e)}, status=status.HTTP_400_BAD_REQUEST)
    
   
    def update(self, request, *args, **kwargs):
        instance = self.get_object()
        serializer = self.get_serializer(instance, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        print(request.data)
        
        # Verificar si se proporciona un nuevo archivo adjunto
        if 'Ine' in request.data:
            Ine = request.data['Ine']
            archivo = instance.Ine
            eliminar_archivo_s3(archivo)
            instance.Ine = Ine  # Actualizar el archivo adjunto sin eliminar el anterior
            
        if 'Comp_dom' in request.data:
            Comp_dom = request.data['Comp_dom']
            archivo = instance.Comp_dom
            print(archivo)
            eliminar_archivo_s3(archivo)
            instance.Comp_dom = Comp_dom  # Actualizar el archivo adjunto sin eliminar el anterior
            
        if 'Rfc' in request.data:
            Rfc = request.data['Rfc']
            archivo = instance.Rfc
            eliminar_archivo_s3(archivo)
            instance.Rfc = Rfc  # Actualizar el archivo adjunto sin eliminar el anterior
        
        if 'Extras' in request.data:
            Extras = request.data['Extras']
            archivo = instance.Extras
            eliminar_archivo_s3(archivo)
            instance.Extras = Extras  # Actualizar el archivo adjunto sin eliminar el anterior
        
        if 'Ingresos' in request.data:
            Ingresos = request.data['Ingresos']
            Ingresos = request.data['Ingresos']
            instance.Ingresos = Ingresos  # Actualizar el archivo adjunto sin eliminar el anterior
        
        if 'Recomendacion_laboral' in request.data:
            Recomendacion_laboral = request.data['Recomendacion_laboral']
            archivo = instance.Recomendacion_laboral
            eliminar_archivo_s3(archivo)
            instance.Recomendacion_laboral = Recomendacion_laboral  # Actualizar el archivo adjunto sin eliminar el anterior
        
       
        serializer.update(instance, serializer.validated_data)
        print(serializer.data['Ine'])# Actualizar el archivo adjunto sin eliminar el anterior
        print(serializer)# Actualizar el archivo adjunto sin eliminar el anterior
        return Response(serializer.data)
