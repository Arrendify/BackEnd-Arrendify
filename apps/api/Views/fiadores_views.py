from rest_framework.decorators import api_view
from rest_framework.response import Response
from rest_framework import viewsets
from rest_framework import status
from rest_framework.authentication import TokenAuthentication,SessionAuthentication
from rest_framework.permissions import IsAuthenticated, AllowAny
#nuevo modelo user
from ...home.models import Aval
from ..views import *
from ..serializers import *
from ...accounts.models import CustomUser
User = CustomUser

#obtener Logs de errores
import logging
import sys
logger = logging.getLogger(__name__)

# Heath Check
from django.http import JsonResponse


class AvalViewSet(viewsets.ModelViewSet):
    authentication_classes = [TokenAuthentication, SessionAuthentication]
    permission_classes = [IsAuthenticated]
    
    queryset = Aval.objects.all()
    serializer_class = AvalSerializer
    lookup_field = 'slug'
    
    
    def list(self, request, *args, **kwargs):
        user_session = request.user       
        try:
           if user_session.is_staff:
                print("Esta entrando a listar aval fill")
                fiadores_obligados =  Aval.objects.all()
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
                fiadores_mios = Aval.objects.filter(user_id = user_session)
                fiadores_obligados =  Aval.objects.filter(inquilino_id__in = inquilinos_all.values("id"))
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
                
                fiadores_mios = Aval.objects.filter(user_id = user_session)
                fiadores_obligados =  Aval.objects.filter(inquilino_id__in = inquilinos_all.values("id"))
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
                print("Esta entrando a listar aval fill")
                fiadores_obligados =  Aval.objects.all().filter(user_id = user_session)
                serializer = self.get_serializer(fiadores_obligados, many=True)
           
           return Response(serializer.data, status= status.HTTP_200_OK)
        except Exception as e:
            return Response({'error': str(e)}, status=status.HTTP_400_BAD_REQUEST)
        
    def create(self, request, *args, **kwargs):
        user_session = request.user
        try:
            print("Llegando a create fiador-obligado")
            print(request.data)
            aval_serializer = self.serializer_class(data=request.data) #Usa el serializer_class
            if aval_serializer.is_valid(raise_exception=True):
                aval_serializer.save( user = user_session)
                print("Guardado Aval")
                return Response({'Aval': aval_serializer.data}, status=status.HTTP_201_CREATED)
            else:
                print("Error en validacion")
                return Response({'errors': aval_serializer.errors})
        except Exception as e:
            return Response({'error': str(e)}, status=status.HTTP_400_BAD_REQUEST)
        

    def update(self, request, *args, **kwargs):
        try:
            print("Esta entrando a actualizar aval")
            instance = self.get_object()
            print("Instance",instance)
            AvalSerializer = self.get_serializer(instance, data=request.data, partial=True)
            AvalSerializer.is_valid(raise_exception=True)
            self.perform_update(AvalSerializer)
            print("Guardado Aval")
            return Response(AvalSerializer.data, status=status.HTTP_200_OK)
            
            print("No guardo Aval")
        except Exception as e: 
            exc_type, exc_obj, exc_tb = sys.exc_info()
            logger.error(f"{datetime.now()} Ocurrió un error en el archivo {exc_tb.tb_frame.f_code.co_filename}, en el método {exc_tb.tb_frame.f_code.co_name}, en la línea {exc_tb.tb_lineno}: {e}")
            return Response({'error': str(e)}, status=status.HTTP_400_BAD_REQUEST)

        
    def retrieve(self, request, slug=None, *args, **kwargs):
        user_session = request.user
        try:
            print("Entrando a retrieve")
            modelos = Aval.objects.all().filter(user_id = user_session) #Toma los datos de Inmuebles.objects.all() que esta al inicio de la clase viewset
            aval = modelos.filter(slug=slug)
            if aval:
                serializer_aval = AvalSerializer(aval, many=True)
                return Response(serializer_aval.data, status=status.HTTP_200_OK)
            else:
                return Response({'message': 'No hay persona fisica con esos datos'}, status = status.HTTP_400_BAD_REQUEST)
        except Exception as e:
            return Response({'error': str(e)}, status=status.HTTP_400_BAD_REQUEST)
        
    def destroy (self,request, *args, **kwargs):
        try:
            aval = self.get_object()
            if aval:
                aval.delete()
                return Response({'message': 'Aval eliminado'}, status=204)
            return Response({'message': 'Error al eliminar'}, status=400)
        except Exception as e:
            return Response({'error': str(e)}, status=status.HTTP_400_BAD_REQUEST)
        
class DocumentosFoo(viewsets.ModelViewSet):
    authentication_classes = [TokenAuthentication, SessionAuthentication]
    permission_classes = [IsAuthenticated]
    
    queryset = DocumentosFiador.objects.all()
    serializer_class = DFSerializer
   
    
    def list(self, request, *args, **kwargs):
        content = {
            'user': str(request.user),
            'auth': str(request.auth),
        }
        queryset = self.filter_queryset(self.get_queryset())
        FiadorSerializers = self.get_serializer(queryset, many=True)
       
        return Response(FiadorSerializers.data ,status=status.HTTP_200_OK)
    
    def create (self, request, *args,**kwargs):
        user_session = request.user.id
        print(user_session)
        try: 
            data = request.data
            print("primer print",data)
            data = {
                    "Ine": request.FILES.get('Ine', None),
                    "Comp_dom": request.FILES.get('Comp_dom', None),
                    "Escrituras": request.FILES.get('Escrituras', None),
                    "Estado_cuenta": request.FILES.get('Estado_cuenta', None),
                    "Fiador":request.data['Fiador'],
                    "user":user_session
                }
            print("segundo print",data)
            if data:
                documentos_serializer = self.get_serializer(data=data)
                documentos_serializer.is_valid(raise_exception=True)
                documentos_serializer.save()
                return Response(documentos_serializer.data, status=status.HTTP_201_CREATED)
            else:
                return Response({'error': 'No file provided'}, status=status.HTTP_400_BAD_REQUEST)
        except Exception as e:
            return Response({'error': str(e)}, status=status.HTTP_400_BAD_REQUEST)
        

    def destroy(self, request, pk=None, *args, **kwargs):
        # try:
        documentos_fiador = self.get_object()
        documento_fiador_serializer = self.serializer_class(documentos_fiador)
        print("Soy ine", documento_fiador_serializer.data['ine'])
        print("1")
        if documentos_fiador:
            ine = documento_fiador_serializer.data['ine']
            print("Soy ine 2", ine)
            comp_dom= documento_fiador_serializer.data['comp_dom']
            rfc= documento_fiador_serializer.data['escrituras_titulo']
            print("Soy RFC", rfc)
            ruta_ine = 'apps/static'+ ine
            print("Ruta ine", ruta_ine)
            ruta_comprobante_domicilio = 'apps/static'+ comp_dom
            ruta_rfc = 'apps/static'+ rfc
            print("Ruta com", ruta_comprobante_domicilio)
            print("Ruta RFC", ruta_rfc)
            os.remove(ruta_ine)
            os.remove(ruta_comprobante_domicilio)
            os.remove(ruta_rfc)
            # self.perform_destroy(documentos_arrendador)  #Tambien se puede eliminar asi
            documentos_fiador.delete()
            return Response({'message': 'Archivo eliminado correctamente'}, status=status.HTTP_200_OK)
        else:
            return Response({'message': 'Error al eliminar archivo'}, status=status.HTTP_400_BAD_REQUEST)
        # except Exception as e:
        #     return Response({'error': str(e)}, status=status.HTTP_400_BAD_REQUEST)
        
        
    def retrieve(self, request, pk=None):
        try:
            documentos = self.queryset #Toma los datos de Inmuebles.objects.all() que esta al inicio de la clase viewset
            fiador = documentos.filter(id=pk)
            serializer_fiador = DFSerializer(fiador, many=True)
            print(serializer_fiador.data)
            ine = serializer_fiador.data[0]['Ine']
            print(ine)
            # documentos_arrendador = self.get_object()
            # print(documentos_arrendador)
            return Response(serializer_fiador.data)
        except Exception as e:
            return Response({'error': str(e)}, status=status.HTTP_400_BAD_REQUEST)
    
    
    def update(self, request, *args, **kwargs):
        instance = self.get_object()
        serializer = self.get_serializer(instance, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        print(request.data)
        
        # Verificar si se proporciona un nuevo archivo adjunto
        if 'Ine' in request.data:
            print("soy ine")
            Ine = request.data['Ine']
            archivo = instance.Ine
            eliminar_archivo_s3(archivo)
            instance.Ine = Ine  # Actualizar el archivo adjunto sin eliminar el anterior
            
        if 'Comp_dom' in request.data:
            Comp_dom = request.data['Comp_dom']
            archivo = instance.Comp_dom
            eliminar_archivo_s3(archivo)
            instance.Comp_dom = Comp_dom  # Actualizar el archivo adjunto sin eliminar el anterior
            
        if 'Estado_cuenta' in request.data:
            Estado_cuenta = request.data['Estado_cuenta']
            instance.Estado_cuenta = Estado_cuenta  # Actualizar el archivo adjunto sin eliminar el anterior
        
        if 'Escrituras' in request.data:
            Escrituras = request.data['Escrituras']
            archivo = instance.Escrituras
            eliminar_archivo_s3(archivo)
            instance.Escrituras = Escrituras  # Actualizar el archivo adjunto sin eliminar el anterior
        
        serializer.update(instance, serializer.validated_data)
        print(serializer.data['Ine'])# Actualizar el archivo adjunto sin eliminar el anterior
        return Response(serializer.data)    