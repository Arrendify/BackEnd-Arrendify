#Django RF
from django.shortcuts import render, get_object_or_404
from rest_framework.response import Response
from rest_framework import status
from rest_framework import viewsets

from ...home.models import *
from ..serializers import *

#nuevo mod user
from ...accounts.models import CustomUser
User = CustomUser

# metodos s3
from ..views import eliminar_archivo_s3

#obtener Logs de errores
import logging
import sys
logger = logging.getLogger(__name__)

# Token
from django.contrib.auth.tokens import default_token_generator
from rest_framework.authentication import TokenAuthentication,SessionAuthentication
from rest_framework.permissions import IsAuthenticated

# ---------------------------------- Inmuebles ---------------------------------- #
class inmueblesViewSet(viewsets.ModelViewSet):
    authentication_classes = [TokenAuthentication, SessionAuthentication]
    permission_classes = [IsAuthenticated]
    
    lookup_field = 'slug'
    queryset = Inmuebles.objects.all()
    serializer_class = InmueblesSerializer
    queryset_imagenes = DocumentosInmueble.objects.all()
    serializer_class_imagen = DocumentosInmuebleSerializer

    def list(self, request):
        user_session = self.request.user
        if user_session.is_staff:
            inmueble = Inmuebles.objects.all()
            data_serializer = self.serializer_class(inmueble, many=True)
            return Response(data_serializer.data)
        
        elif user_session.rol == "Inmobiliaria":  
                #tengo que busca a los arrendadores que tiene a un agente vinculado
                print("soy inmobiliaria", user_session.name_inmobiliaria)
                agentes = User.objects.all().filter(pertenece_a = user_session.name_inmobiliaria) 
                
                #busqueda de arrendadores propios y registrados por mis agentes
                arrendadores_a_cargo = Propietario.objects.filter(user_id__in = agentes)
                arrendadores_mios = Propietario.objects.filter(user_id = user_session)
                mios = arrendadores_a_cargo.union(arrendadores_mios)
               
                #busqueda de inquilino vinculado
                pertenece2 = Propietario.objects.filter(mi_agente_es__icontains = agentes.values("first_name"))
                pertenece = Propietario.objects.filter(mi_agente_es__in = agentes.values("first_name"))
                pertenece = pertenece.union(pertenece2)
                arrendadores_all = mios.union(pertenece)
                print("Registrados por mi o por un agente directo", mios)
                print("Independientes vinculado(s) a un agente(s)", pertenece)
                print("arrendador_all", arrendadores_all)
                print("arrendador_all con ids",arrendadores_all.values("id"))
                
                #toca obtener los inmuebles propios y de los agentes e inquilinos
                inmuebles_mios = Inmuebles.objects.filter(user_id = user_session)
                print("paso1",inmuebles_mios)
                inmuebles =  Inmuebles.objects.filter(arrendador_id__in = arrendadores_all.values("id"))
                print("paso2",)
                inmuebles_all = inmuebles.union(inmuebles_mios)
                print("paso3")
                serializer = self.get_serializer(inmuebles_all, many=True)
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
            arrendadores_ag = Propietario.objects.filter(user_id = user_session)
            #tengo que obtener a mis inquilinos vinculados
            pertenece2 = Propietario.objects.filter(mi_agente_es__icontains = user_session.first_name)
            pertenece = Propietario.objects.filter(mi_agente_es__in = user_session.first_name)
            pertenece = pertenece.union(pertenece2)
            arrendadores_all = arrendadores_ag.union(pertenece)
            print("mis arrendadores propios:",arrendadores_ag)
            print("mis arrendadores vinculados:",pertenece)
            print("todos mis arrendadores:",arrendadores_all)
            
            #toca obtener los inmuebles propios y de los agentes e inquilinos
            inmuebles_mios = Inmuebles.objects.filter(user_id = user_session)
            print("paso1",inmuebles_mios)
            inmuebles =  Inmuebles.objects.filter(arrendador_id__in = arrendadores_all.values("id"))
            print("paso2",)
            inmuebles_all = inmuebles.union(inmuebles_mios)
            print("paso3")
            serializer = self.get_serializer(inmuebles_all, many=True)
            serialized_data = serializer.data
            
            if not serialized_data:
                print("no hay datos mi carnal")
                return Response({"message": "No hay datos disponibles",'asunto' :'2'})

            for item in serialized_data:
                item['agente'] = True
                
            return Response(serialized_data)
    
        else:            
            user_id = self.request.user.id
            snippets = Inmuebles.objects.filter(user_id=user_id)
            data_serializer = self.serializer_class(snippets, many=True)
            return Response(data_serializer.data)

    def create (self, request, *args, **kwargs):
        try:
            data_documentos = {}
            data = request.data
            print("Esta llegando a create")
            print("id user es:",request.user.id)
            print("paso 2")
            print("request data",data)
                
            inmueble_serializer = self.get_serializer(data=data) #Usa el serializer_class para verificar que se  correcto
            if inmueble_serializer.is_valid(raise_exception=True):
                documentos = ['predial', 'escrituras', 'reglamento_interno']
                print("antes del for",data_documentos)
                for field in documentos:
                    print("campo",field)
                    if field in request.FILES:
                        data_documentos[field] = request.FILES[field]
                    else:
                        data_documentos[field] = None
                
                print("ya tengo los documentos",data_documentos)
                inmueble = inmueble_serializer.save(user = request.user)
                data_documentos["inmueble"] = inmueble.id
                #data_documentos["user"] = request.user
                
                print("serializer",data_documentos)
                documentos_serializer = DocumentosInmuebleSerializer(data=data_documentos)
                documentos_serializer.is_valid(raise_exception=True)
                documentos_serializer.save(user = request.user)
                print("inmuble guardado")
                return Response({'inmueble': inmueble_serializer.data}, status=status.HTTP_201_CREATED)
                
            else:
                print("Error al crear inmueble",inmueble_serializer.errors)
                return Response({"error serializer no valido":inmueble_serializer.errors}, status = status.HTTP_400_BAD_REQUEST)
        except Exception as e:
            print(f"el error es: {e}")
            exc_type, exc_obj, exc_tb = sys.exc_info()
            logger.error(f"{datetime.now()} Ocurrió un error en el archivo {exc_tb.tb_frame.f_code.co_filename}, en el método {exc_tb.tb_frame.f_code.co_name}, en la línea {exc_tb.tb_lineno}:  {e}")
            return Response({'error_exept': str(e)}, status = status.HTTP_302_FOUND)

    
    def destroy(self, request, slug=None, *args, **kwargs):
        try:
            print("Esta entrando a eliminar Inmueble")
            inmueble = get_object_or_404(Inmuebles.objects.all(), slug=slug)
            print("Soy inmueble", inmueble)
            if inmueble:
                inmueble.delete()
                print("Elimino correctamente")
                return Response({'message': 'Inmueble eliminado correctamente'}, status=204)
            return Response({'message': 'Error al eliminar inmueble'}, status=400)
        except Exception as e:
            exc_type, exc_obj, exc_tb = sys.exc_info()
            logger.error(f"{datetime.now()} Ocurrió un error en el archivo {exc_tb.tb_frame.f_code.co_filename}, en el método {exc_tb.tb_frame.f_code.co_name}, en la línea {exc_tb.tb_lineno}: {e}")
            return Response({'error': str(e)}, status=status.HTTP_400_BAD_REQUEST)
        
    def retrieve(self, request, slug=None, *args, **kwargs):
        try:
            print("Entrando a retrieve")
            #Toma los datos de Inmuebles.objects.all() que esta al inicio de la clase viewset
            inmueble = Inmuebles.objects.all().filter(slug=slug)
            serializer_inmueble = InmueblesSerializer(inmueble, many=True)
            id = serializer_inmueble.data[0]['id']
            imagenes = self.queryset_imagenes.filter(inmueble_id=id)
            serializer_img = DocumentosInmuebleSerializer(imagenes, many=True)
            total_imagenes = imagenes.count()
     
            dta = {}
            dta['inmueble'] = serializer_inmueble.data
            dta['fotos'] = serializer_img.data
            dta['total_imagenes'] = total_imagenes
            # data = {'data': context}
            # return render(request, 'home/edit_inmueble.html', {'data': dta})
            return Response({'inmuebles': serializer_inmueble.data, 'imagen': serializer_img.data, 'total_imagenes':total_imagenes},
                            status=status.HTTP_201_CREATED)
        except Exception as e:
            exc_type, exc_obj, exc_tb = sys.exc_info()
            logger.error(f"{datetime.now()} Ocurrió un error en el archivo {exc_tb.tb_frame.f_code.co_filename}, en el método {exc_tb.tb_frame.f_code.co_name}, en la línea {exc_tb.tb_lineno}: {e}")
            return Response({'error': str(e)}, status=status.HTTP_400_BAD_REQUEST)
    
    def update(self, request, *args, **kwargs):
        try: 
            print("Esta entrando a update Inmueble")
            partial = kwargs.pop('partial', False)
            data_documentos = {}
            instance = self.get_object()
            instance_docs = self.queryset_imagenes.filter(inmueble_id = instance.id).first()
            print("Soy nuevamente data", request.data)
            print("instance",instance)
            print("instance",instance.id)
            print("partial",partial)

            documentos = ['predial', 'escrituras', 'reglamento_interno']
            for field in documentos:
                print("campo",field)
                if field in request.FILES:
                    data_documentos[field] = request.FILES[field]
                    archivo = getattr(instance_docs, field, None)
                    eliminar_archivo_s3(archivo)
                    print(archivo)
                    
            print("instancia documetos",instance_docs)
            print("ya tengo los documentos",data_documentos)
       
            if len(data_documentos) != 0:
                print("tenemos que guardar lo nuevo")
                documentos_serializer = DocumentosInmuebleSerializer(instance_docs, data=data_documentos, partial=True)
                documentos_serializer.is_valid(raise_exception=True)
                documentos_serializer.update(instance_docs, documentos_serializer.validated_data)
                print("actualizamos documentos")

           
            serializer = self.get_serializer(instance, data=request.data, partial=partial)
    
            if serializer.is_valid(raise_exception=True):
                self.perform_update(serializer)
                print("Actualizamos correctamente el inmueble")
                return Response({'inmueble': serializer.data}, status=status.HTTP_201_CREATED)
            else:
                return Response({'error': "error de validacion de serializer"}, status=status.HTTP_400_BAD_REQUEST)   
            
        except Exception as e:
            print(f"el error es: {e}")
            exc_type, exc_obj, exc_tb = sys.exc_info()
            logger.error(f"{datetime.now()} Ocurrió un error en el archivo {exc_tb.tb_frame.f_code.co_filename}, en el método {exc_tb.tb_frame.f_code.co_name}, en la línea {exc_tb.tb_lineno}:  {e}")
            return Response({'error_exept': str(e)}, status = status.HTTP_302_FOUND)    

#  --------------------------------------------------------  Mobiliario -----------------------------------------------------------

class MobiliarioCantidad(viewsets.ModelViewSet):
    authentication_classes = [TokenAuthentication, SessionAuthentication]
    queryset = InmueblesInmobiliario.objects.all()
    serializer_class = InmueblesMobiliarioSerializer

    def create(self, request, *args, **kwargs):
        print("Soy request", request.data)   
        datos = request.data["datos"]
        print("soy datos",datos)
        print("cantidad",datos[0]["cantidad"])
        
    
        # Eliminar los campos vacíos del diccionario 'data'
        # data = {key: value for key, value in data.items() if value != ''}
        for mobiliario_nuevo in datos:                                 
            data2 = {
            "cantidad": mobiliario_nuevo["cantidad"],
            "mobiliario": mobiliario_nuevo["mobiliario"],
            "observaciones": mobiliario_nuevo["observaciones"],
            "inmuebles": request.data["inmueble"],
            }
            print("obtube los datos",data2)
            print("antes de mobiliario")
            mobiliario = InmueblesMobiliarioSerializer(data=data2)
            print("despues de mobiliario",mobiliario)
            
            mobiliario.is_valid(raise_exception=True)
            print("mobiliario es valido")
            mobiliario.save(user = request.user)
            print(f"Guarde => cantidad: {mobiliario_nuevo['cantidad']}, cantidad: {mobiliario_nuevo['mobiliario']} ,observaciones: {mobiliario_nuevo['cantidad']}")


        return Response(mobiliario.data, status=status.HTTP_201_CREATED)