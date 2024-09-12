#DRF
from rest_framework.decorators import api_view
from rest_framework.response import Response
from rest_framework import viewsets
from rest_framework import status
from rest_framework.authentication import TokenAuthentication,SessionAuthentication
from rest_framework.permissions import IsAuthenticated, AllowAny

#modelos
from ...home.models import inquilino_personafisica, inquilino_personamoral, Inquilino
from ..serializers import *
from ...accounts.models import CustomUser
User = CustomUser

#obtener Logs de errores
import logging
import sys
logger = logging.getLogger(__name__)


@api_view(['GET'])
def inquilinos_list_all(request):
    """
    List all code snippets, or create a new snippet.
    """
    user_session = request.user
    try:    
        if request.method == 'GET':
            if user_session.is_staff:
                snippets = Inquilino.objects.all().order_by('-id')
                
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
                inquilinos_a_cargo = Inquilino.objects.filter(user_id__in = agentes)
                inquilinos_mios = Inquilino.objects.filter(user_id = user_session)
                print("mis registros propios como inmobiliaria",inquilinos_mios)
                mios = inquilinos_a_cargo.union(inquilinos_mios)
                
                #busqueda de inquilino vinculado
                pertenece2 = Inquilino.objects.filter(mi_agente_es__icontains = agentes.values("first_name"))
                pertenece = Inquilino.objects.filter(mi_agente_es__in = agentes.values("first_name"))
                pertenece = pertenece.union(pertenece2)
                
                inquilinos_all = mios.union(pertenece)
                #print("inquilinos a cargo", inquilinos_a_cargo.values())
                print("Registrados por mi o por un agente directo", mios)
                print("Independientes vinculado(s) a un agente(s)", pertenece)
                print("inquilinos_all",inquilinos_all)
                
                
                serializer = InquilinoSerializers(inquilinos_all, many=True)
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
                inquilinos_ag = Inquilino.objects.filter(user_id = user_session)
                #obtengo mis inquilinos vinculados
                pertenece = Inquilino.objects.filter(mi_agente_es__icontains = user_session.first_name)
                # pertenece = Inquilino.objects.filter(mi_agente_es = user_session.first_name)
                # pertenece = Inquilino.objects.filter(mi_agente_es__in = user_session.first_name)
                # pertenece = pertenece.union(pertenece2)
                inquilinos_all = inquilinos_ag.union(pertenece)
                serializer = InquilinoSerializers(inquilinos_all, many=True)
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
                inquilinos_propios = Inquilino.objects.all().filter(user_id = user_session)
                print(inquilinos_propios)
                
                # Obtener todos los arrendadores amigos del usuario actual
                arrendadores_amigos = Arrendador.objects.all().filter(user_id = user_session)
                print(arrendadores_amigos)
                # Obtener inquilinos ligados a los arrendadores amigos
                inquilinos_amigos = Inquilino.objects.filter(amigo_inquilino__receiver__in = arrendadores_amigos)
                print(inquilinos_amigos)
                # Combinar inquilinos propios e inquilinos amigos sin duplicados basados en el ID
                snippets = inquilinos_propios.union(inquilinos_amigos)
                print(snippets)
                
                serializer = InquilinoSerializers(snippets, many=True)
        
                return Response(serializer.data)
    except Exception as e:
        print(f"el error es: {e}")
        exc_type, exc_obj, exc_tb = sys.exc_info()
        logger.error(f"{datetime.now()} Ocurrió un error en el archivo {exc_tb.tb_frame.f_code.co_filename}, en el método {exc_tb.tb_frame.f_code.co_name}, en la línea {exc_tb.tb_lineno}:  {e}")
        return Response({'error': str(e)}, status=status.HTTP_400_BAD_REQUEST)
    
    
class inquilinos_nuevo(viewsets.ModelViewSet):
    authentication_classes = [TokenAuthentication, SessionAuthentication]
    permission_classes = [IsAuthenticated]    
    
    def list(self, request, *args, **kwargs):
        user_session = request.user       
        try:
            #tenemos que obtener los 2 tipos de inquilino o cada tipo dependiendo del filtro
           if user_session.is_staff:
                print("Esta entrando a listar fiador_obligado fil")
                fiadores_obligados =  Fiador_obligado.objects.all()
                serializer = self.get_serializer(fiadores_obligados, many=True)
                serialized_data = serializer.data
                
                # Agregar el campo 'is_staff' en el arreglo de user
                for item in serialized_data:
                    item['user']['is_staff'] = True
                
                return Response(serialized_data)
            
           elif user_session.rol == "Inmobiliaria":  
                #tengo que busca a los inquilinos que tiene a un agente vinculado
                print("soy inmobiliaria", user_session.name_inmobiliaria)
                agentes = User.objects.all().filter(pertenece_a = user_session.name_inmobiliaria) 
                
                #busqueda de inquilino propios y registrados por mis agentes
                inquilinos_a_cargo = Inquilino.objects.filter(user_id__in = agentes)
                inquilinos_mios = Inquilino.objects.filter(user_id = user_session)
                mios = inquilinos_a_cargo.union(inquilinos_mios)
               
                #busqueda de inquilino vinculado
                pertenece2 = Inquilino.objects.filter(mi_agente_es__icontains = agentes.values("first_name"))
                pertenece = Inquilino.objects.filter(mi_agente_es__in = agentes.values("first_name"))
                pertenece = pertenece.union(pertenece2)
                inquilinos_all = mios.union(pertenece)
                print("Registrados por mi o por un agente directo", mios)
                print("Independientes vinculado(s) a un agente(s)", pertenece)
                print("inquilinos_all",inquilinos_all)
                print("inquilinos_all con ids",inquilinos_all.values("id"))
                
                #toca obtener los fiadores propios y de los agentes e inquilinos
                fiadores_mios = Fiador_obligado.objects.filter(user_id = user_session)
                fiadores_obligados =  Fiador_obligado.objects.filter(inquilino_id__in = inquilinos_all.values("id"))
                fiadores_all = fiadores_obligados.union(fiadores_mios)
                serializer = self.get_serializer(fiadores_all, many=True)
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
                inquilinos_ag = Inquilino.objects.filter(user_id = user_session)
                #tengo que obtener a mis inquilinos vinculados
                pertenece2 = Inquilino.objects.filter(mi_agente_es__icontains = user_session.first_name)
                pertenece = Inquilino.objects.filter(mi_agente_es__in = user_session.first_name)
                pertenece = pertenece.union(pertenece2)
                inquilinos_all = inquilinos_ag.union(pertenece)
                print("mis inquilinos propios:",inquilinos_ag)
                print("mis inquilinos vinculados:",pertenece)
                print("todos mis inquilinos:",inquilinos_all)
                
                fiadores_mios = Fiador_obligado.objects.filter(user_id = user_session)
                fiadores_obligados =  Fiador_obligado.objects.filter(inquilino_id__in = inquilinos_all.values("id"))
                fiadores_all = fiadores_obligados.union(fiadores_mios)
                serializer = self.get_serializer(fiadores_all, many=True)
                serialized_data = serializer.data
                
                if not serialized_data:
                    print("no hay datos mi carnal")
                    return Response({"message": "No hay datos disponibles",'asunto' :'2'})

                for item in serialized_data:
                    item['agente'] = True
                    
                return Response(serialized_data)
           else:
                print("Esta entrando a listar fiador_obligado fil")
                fiadores_obligados =  Fiador_obligado.objects.all().filter(user_id = user_session)
                serializer = self.get_serializer(fiadores_obligados, many=True)
           
           return Response(serializer.data, status= status.HTTP_200_OK)
        except Exception as e:
            return Response({'error': str(e)}, status=status.HTTP_400_BAD_REQUEST)
        
    def registro_ipf(self, request, *args, **kwargs):
        user_session = request.user
        try:
            print("Registro Persona Fisica Inquilino")
            print("Datos recibidos",request.data)
            ipf_serializer = IPF_Serializer(data=request.data)
           
            if ipf_serializer.is_valid(raise_exception=True):
                ipf_serializer.save( user = user_session)
                print("Guardado Al inquilino")
                return Response({'inquilino_pf': ipf_serializer.data}, status=status.HTTP_201_CREATED)
            else:
                print("Error en validacion")
                return Response({'errors': ipf_serializer.errors})
        except Exception as e:
            return Response({'error': str(e)}, status=status.HTTP_400_BAD_REQUEST)
    
    #Ver como lo implemento
    def retomar_registro_ipf(self, request, *args, **kwargs):
        try:
            print("Esta entrando retomar registo ipf")
            partial = kwargs.pop('partial', False)
            print("partials",partial)
            print(request.data)
            #analizar como funciona esto
            instance = self.get_object()
            print("instance",instance)
            
            serializer = self.get_serializer(instance, data=request.data, partial=partial)
            print(serializer)
            if serializer.is_valid(raise_exception=True):
                self.perform_update(serializer)
                print("edito fiador obligado")
                # return redirect('myapp:my-url')
                return Response(serializer.data, status=status.HTTP_200_OK)
            else:
                return Response({'errors': serializer.errors})
        except Exception as e:
            return Response({'error': str(e)}, status=status.HTTP_400_BAD_REQUEST)
    
    
    def update(self, request, *args, **kwargs):
        try:
            print("Esta entrando a actualizar fiador_obligado")
            partial = kwargs.pop('partial', False)
            print("partials",partial)
            print(request.data)
            instance = self.get_object()
            print("instance",instance)
            serializer = self.get_serializer(instance, data=request.data, partial=partial)
            print(serializer)
            if serializer.is_valid(raise_exception=True):
                self.perform_update(serializer)
                print("edito fiador obligado")
                # return redirect('myapp:my-url')
                return Response(serializer.data, status=status.HTTP_200_OK)
            else:
                return Response({'errors': serializer.errors})
        except Exception as e:
            return Response({'error': str(e)}, status=status.HTTP_400_BAD_REQUEST)
        
    def retrieve(self, request, slug=None, *args, **kwargs):
        user_session = request.user
        try:
            print("Entrando a retrieve")
            modelos = Fiador_obligado.objects.all().filter(user_id = user_session) #Toma los datos de Inmuebles.objects.all() que esta al inicio de la clase viewset
            fiador_obligado = modelos.filter(slug=slug)
            if fiador_obligado:
                serializer_fiador_obligado = Fiador_obligadoSerializer(fiador_obligado, many=True)
                return Response(serializer_fiador_obligado.data, status=status.HTTP_200_OK)
            else:
                return Response({'message': 'No hay persona fisica con esos datos'}, status = status.HTTP_400_BAD_REQUEST)
        except Exception as e:
            return Response({'error': str(e)}, status=status.HTTP_400_BAD_REQUEST)
        
    def destroy (self,request, *args, **kwargs):
        try:
            fiador_obligado = self.get_object()
            if fiador_obligado:
                fiador_obligado.delete()
                return Response({'message': 'Fiador obligado eliminado'}, status=204)
            return Response({'message': 'Error al eliminar'}, status=400)
        except Exception as e:
            return Response({'error': str(e)}, status=status.HTTP_400_BAD_REQUEST)
