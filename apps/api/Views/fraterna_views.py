from rest_framework.decorators import api_view
from rest_framework.views import APIView
from rest_framework import viewsets
from rest_framework.response import Response
from ...home.models import *
from ..serializers import *
from rest_framework import status
from ...accounts.models import CustomUser
User = CustomUser
from rest_framework.authentication import TokenAuthentication,SessionAuthentication
from rest_framework.permissions import IsAuthenticated, AllowAny
from django.http import HttpResponse

#s3
import boto3
from botocore.exceptions import ClientError
from botocore.exceptions import NoCredentialsError
from django.db.models import Q
from core.settings import AWS_ACCESS_KEY_ID, AWS_SECRET_ACCESS_KEY
#weasyprint
from weasyprint import HTML, CSS
from django.template.loader import render_to_string
from django.template.loader import get_template
#Legal
from num2words import num2words
from datetime import date
from datetime import datetime
#Libreria para obtener el lenguaje en español
import locale
#obtener Logs de errores
import logging
import sys
logger = logging.getLogger(__name__)



# ----------------------------------Metodos Extras----------------------------------------------- #
def eliminar_archivo_s3(file_name):
    s3 = boto3.client(
            's3',
            aws_access_key_id=AWS_ACCESS_KEY_ID,
            aws_secret_access_key=AWS_SECRET_ACCESS_KEY
             )
    print("soy el valor de s3",s3.__dict__)
   
    try:
        print("entre en el Try")
        s3.delete_object(Bucket="arrendifystorage", Key=f"static/{str(file_name)}")
        print("El archivo se eliminó correctamente de S3.")
    except NoCredentialsError:
        print("No se encontraron las credenciales de AWS.",{NoCredentialsError})
# ----------------------------------Metodos Extras----------------------------------------------- #

class ResidenteViewSet(viewsets.ModelViewSet):
    authentication_classes = [TokenAuthentication, SessionAuthentication]
    permission_classes = [IsAuthenticated]
    queryset = Residentes.objects.all()
    serializer_class = ResidenteSerializers
    
    def list(self, request, *args, **kwargs):
        user_session = request.user       
        try:
           if user_session.is_staff:
                print("Esta entrando a listar Residentes")
                residentes =  Residentes.objects.all().order_by('id')
                serializer = self.get_serializer(residentes, many=True)
                return Response(serializer.data, status= status.HTTP_200_OK)
            
           elif user_session.rol == "Inmobiliaria":  
                #tengo que busca a los inquilinos que tiene a un agente vinculado
                print("soy inmobiliaria", user_session.name_inmobiliaria)
                agentes = User.objects.all().filter(pertenece_a = user_session.name_inmobiliaria) 
                
                #busqueda de Residentes propios y registrados por mis agentes
                inquilinos_a_cargo = Residentes.objects.filter(user_id__in = agentes)
                inquilinos_mios = Residentes.objects.filter(user_id = user_session)
                mios = inquilinos_a_cargo.union(inquilinos_mios)
                mios = mios.order_by('id')
               
                serializer = self.get_serializer(mios, many=True)
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
                residentes_ag = Residentes.objects.filter(user_id = user_session)
                residentes_ag = residentes_ag.order_by('id')
                #tengo que obtener a mis inquilinos vinculados
              
                serializer = self.get_serializer(residentes_ag, many=True)
                serialized_data = serializer.data
                
                if not serialized_data:
                    print("no hay datos mi carnal")
                    return Response({"message": "No hay datos disponibles",'asunto' :'2'})

                for item in serialized_data:
                    item['agente'] = True
                    
                return Response(serialized_data)
           else:
                print("Esta entrando a listar Residentes fil")
                fiadores_obligados =  Residentes.objects.all().filter(user_id = user_session)
                serializer = self.get_serializer(fiadores_obligados, many=True)
           
           return Response(serializer.data, status= status.HTTP_200_OK)
        except Exception as e:
            print(f"el error es: {e}")
            exc_type, exc_obj, exc_tb = sys.exc_info()
            logger.error(f"{datetime.now()} Ocurrió un error en el archivo {exc_tb.tb_frame.f_code.co_filename}, en el método {exc_tb.tb_frame.f_code.co_name}, en la línea {exc_tb.tb_lineno}:  {e}")
            return Response({'error': str(e)}, status= status.HTTP_400_BAD_REQUEST)
        
    def create(self, request, *args, **kwargs):
        try:
            user_session = request.user
            print("Llegando a create de residentes")
            print(request.data)
            residente_serializer = self.serializer_class(data=request.data) #Usa el serializer_class
            print(residente_serializer)
            if residente_serializer.is_valid(raise_exception=True):
                residente_serializer.save( user = user_session)
                print("Guardado residente")
                return Response({'Residentes': residente_serializer.data}, status=status.HTTP_201_CREATED)
            else:
                print("Error en validacion")
                return Response({'errors': residente_serializer.errors})
        except Exception as e:
            print(f"el error es: {e}")
            exc_type, exc_obj, exc_tb = sys.exc_info()
            logger.error(f"{datetime.now()} Ocurrió un error en el archivo {exc_tb.tb_frame.f_code.co_filename}, en el método {exc_tb.tb_frame.f_code.co_name}, en la línea {exc_tb.tb_lineno}:  {e}")
            return Response({'error': str(e)}, status= status.HTTP_400_BAD_REQUEST)
        

    def update(self, request, *args, **kwargs):
        try:
            print("Esta entrando a actualizar Residentes")
            partial = kwargs.pop('partial', False)
            print("partials",partial)
            print(request.data)
            instance = self.get_object()
            print("instance",instance)
            serializer = self.get_serializer(instance, data=request.data, partial=partial)
            print(serializer)
            if serializer.is_valid(raise_exception=True):
                self.perform_update(serializer)
                print("edito residente")
                # return redirect('myapp:my-url')
                return Response(serializer.data, status=status.HTTP_200_OK)
            else:
                return Response({'errors': serializer.errors})
        except Exception as e:
            print(f"el error es: {e}")
            exc_type, exc_obj, exc_tb = sys.exc_info()
            logger.error(f"{datetime.now()} Ocurrió un error en el archivo {exc_tb.tb_frame.f_code.co_filename}, en el método {exc_tb.tb_frame.f_code.co_name}, en la línea {exc_tb.tb_lineno}:  {e}")
            return Response({'error': str(e)}, status= status.HTTP_400_BAD_REQUEST)
        
    def retrieve(self, request, slug=None, *args, **kwargs):
        try:
            user_session = request.user
            print("Entrando a retrieve")
            modelos = Residentes.objects.all().filter(user_id = user_session) #Toma los datos de Inmuebles.objects.all() que esta al inicio de la clase viewset
            Residentes = modelos.filter(slug=slug)
            if Residentes:
                serializer_Residentes = ResidenteSerializers(Residentes, many=True)
                return Response(serializer_Residentes.data, status=status.HTTP_200_OK)
            else:
                return Response({'message': 'No hay persona fisica con esos datos'}, status = status.HTTP_400_BAD_REQUEST)
        except Exception as e:
            print(f"el error es: {e}")
            exc_type, exc_obj, exc_tb = sys.exc_info()
            logger.error(f"{datetime.now()} Ocurrió un error en el archivo {exc_tb.tb_frame.f_code.co_filename}, en el método {exc_tb.tb_frame.f_code.co_name}, en la línea {exc_tb.tb_lineno}:  {e}")
            return Response({'error': str(e)}, status= status.HTTP_400_BAD_REQUEST)
        
    def destroy (self,request, *args, **kwargs):
        try:
            Residentes = self.get_object()
            if Residentes:
                Residentes.delete()
                return Response({'message': 'Fiador obligado eliminado'}, status=204)
            return Response({'message': 'Error al eliminar'}, status=400)
        except Exception as e:
            return Response({'error': str(e)}, status=status.HTTP_400_BAD_REQUEST)

class DocumentosRes(viewsets.ModelViewSet):
    authentication_classes = [TokenAuthentication, SessionAuthentication]
    permission_classes = [IsAuthenticated]
    
    queryset = DocumentosResidentes.objects.all()
    serializer_class = DRSerializer
   
    def list(self, request, *args, **kwargs):
        try:
            content = {
                'user': str(request.user),
                'auth': str(request.auth),
            }
            queryset = self.filter_queryset(self.get_queryset())
            ResidenteSerializers = self.get_serializer(queryset, many=True)
            return Response(ResidenteSerializers.data ,status=status.HTTP_200_OK)
        
        except Exception as e:
            print(f"el error es: {e}")
            exc_type, exc_obj, exc_tb = sys.exc_info()
            logger.error(f"{datetime.now()} Ocurrió un error en el archivo {exc_tb.tb_frame.f_code.co_filename}, en el método {exc_tb.tb_frame.f_code.co_name}, en la línea {exc_tb.tb_lineno}:  {e}")
            return Response({'error': str(e)}, status= status.HTTP_400_BAD_REQUEST)
    
    def create (self, request, *args,**kwargs):
        try: 
            user_session = str(request.user.id)
            data = request.data
            data = {
                    "Ine": request.FILES.get('Ine', None),
                    "Ine_arr": request.FILES.get('Ine_arr', None),
                    "Comp_dom": request.FILES.get('Comp_dom', None),
                    "Rfc": request.FILES.get('Rfc', None),
                    "Ingresos": request.FILES.get('Ingresos', None),
                    "Extras": request.FILES.get('Extras', None),
                    "Recomendacion_laboral": request.FILES.get('Recomendacion_laboral', None),
                    "residente":request.data['residente'],
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
            print(f"el error es: {e}")
            exc_type, exc_obj, exc_tb = sys.exc_info()
            logger.error(f"{datetime.now()} Ocurrió un error en el archivo {exc_tb.tb_frame.f_code.co_filename}, en el método {exc_tb.tb_frame.f_code.co_name}, en la línea {exc_tb.tb_lineno}:  {e}")
            return Response({'error': str(e)}, status= status.HTTP_400_BAD_REQUEST)
        

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
            if 'Ine' in request.data:
                print("entro aqui")
                Ine = request.data['Ine']
                archivo = instance.Ine
                eliminar_archivo_s3(archivo)
                instance.Ine = Ine  # Actualizar el archivo adjunto sin eliminar el anterior
            
            if 'Ine_arr' in request.data:
                print("arr")
                Ine_arr = request.data['Ine_arr']
                archivo = instance.Ine_arr
                eliminar_archivo_s3(archivo)
                instance.Ine_arr = Ine_arr  # Actualizar el archivo adjunto sin eliminar el anterior
                
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

        
        except Exception as e:
            print(f"el error es: {e}")
            exc_type, exc_obj, exc_tb = sys.exc_info()
            logger.error(f"{datetime.now()} Ocurrió un error en el archivo {exc_tb.tb_frame.f_code.co_filename}, en el método {exc_tb.tb_frame.f_code.co_name}, en la línea {exc_tb.tb_lineno}:  {e}")
            return Response({'error': str(e)}, status= status.HTTP_400_BAD_REQUEST)
        
#////////////////////////CONTRATOS///////////////////////////////
class Contratos_fraterna(viewsets.ModelViewSet):
    # authentication_classes = [TokenAuthentication, SessionAuthentication]
    # permission_classes = [IsAuthenticated]
    queryset = FraternaContratos.objects.all()
    serializer_class = ContratoFraternaSerializer
    
    def list(self, request, *args, **kwargs):
        try:
           user_session = request.user       
           if user_session.is_staff:
               print("Esta entrando a listar cotizacion")
               contratos =  FraternaContratos.objects.all()
               serializer = self.get_serializer(contratos, many=True)
               serialized_data = serializer.data
                
               # Agregar el campo 'is_staff' en el arreglo de user
               for item in serialized_data:
                 item['is_staff'] = True
                
               return Response(serialized_data)
           
           elif user_session.rol == "Inmobiliaria":
               #primero obtenemos mis agentes.
               print("soy inmobiliaria en listar contratos", user_session.name_inmobiliaria)
               agentes = User.objects.all().filter(pertenece_a = user_session.name_inmobiliaria) 
               #obtenemos los contratos
               contratos_mios = FraternaContratos.objects.filter(user_id = user_session.id)
               contratos_agentes = FraternaContratos.objects.filter(user_id__in = agentes.values("id"))
               contratos_all = contratos_mios.union(contratos_agentes)
               
               print("es posible hacer esto:", contratos_all)
               
               serializer = self.get_serializer(contratos_all, many=True)
               return Response(serializer.data, status= status.HTTP_200_OK)
               
           elif user_session.rol == "Agente":
               print(f"soy Agente: {user_session.first_name} en listar contrato")
               residentes_ag = FraternaContratos.objects.filter(user_id = user_session)
              
               serializer = self.get_serializer(residentes_ag, many=True)
               return Response(serializer.data, status= status.HTTP_200_OK)
                 
           else:
               print(f"soy normalito: {user_session.first_name} en listar contrato")
               residentes_ag = FraternaContratos.objects.filter(user_id = user_session)
              
               serializer = self.get_serializer(residentes_ag, many=True)
               return Response(serializer.data, status= status.HTTP_200_OK)
           
           
        except Exception as e:
            print(f"el error es: {e}")
            exc_type, exc_obj, exc_tb = sys.exc_info()
            logger.error(f"{datetime.now()} Ocurrió un error en el archivo {exc_tb.tb_frame.f_code.co_filename}, en el método {exc_tb.tb_frame.f_code.co_name}, en la línea {exc_tb.tb_lineno}:  {e}")
            return Response({'error': str(e)}, status= status.HTTP_400_BAD_REQUEST)
        
    def create(self, request, *args, **kwargs):
        try:
            user_session = request.user
            print(user_session)
            print("RD",request.data)
            print("Request",request)
            print("Llegando a create de contrato para fraterna")
            
            fecha_actual = date.today()
            contrato_serializer = self.serializer_class(data = request.data) #Usa el serializer_class
            if contrato_serializer.is_valid():
                nuevo_proceso = ProcesoContrato.objects.create(usuario = user_session, fecha = fecha_actual, status_proceso = "En Revisión")
                if nuevo_proceso:
                    print("ya la armamos")
                    print(nuevo_proceso.id)
                    info = contrato_serializer.save(user = user_session)
                    nuevo_proceso.contrato = info
                    nuevo_proceso.save()
                    print("Se Guardado solicitud")
                    return Response({'Residentes': contrato_serializer.data}, status=status.HTTP_201_CREATED)
                else:
                    print("no se creo el proceso")
                    return Response({'msj':'no se creo el proceso'}, status=status.HTTP_204_NO_CONTENT) 
            
            else:
                print("serializer no valido")
                return Response({'msj':'no es valido el serializer'}, status=status.HTTP_204_NO_CONTENT)     
            
        
        except Exception as e:
            print(f"el error es: {e}")
            exc_type, exc_obj, exc_tb = sys.exc_info()
            logger.error(f"{datetime.now()} Ocurrió un error en el archivo {exc_tb.tb_frame.f_code.co_filename}, en el método {exc_tb.tb_frame.f_code.co_name}, en la línea {exc_tb.tb_lineno}:  {e}")
            return Response({'error': str(e)}, status= status.HTTP_400_BAD_REQUEST)
    
    def update(self, request, *args, **kwargs):
        try:
            #primero verificamos que tenga contadores activos
            print("Esta entrando a actualizar Contratos Fraterna")
            partial = kwargs.pop('partial', False)
            instance = self.get_object()
           
            # Verificar si se proporciona un nuevo archivo adjunto
            if 'plano_localizacion' in request.data:
                print("entro aqui")
                nuevo = request.data['plano_localizacion']
                archivo = instance.plano_localizacion
                eliminar_archivo_s3(archivo)
                instance.plano_localizacion = nuevo  # Actualizar el archivo adjunto sin eliminar el anterior
                        
            proceso = ProcesoContrato.objects.all().get(contrato_id = instance.id)
            print("el contador es: ",proceso.contador)
            if (proceso.contador > 0 ):
                serializer = self.get_serializer(instance, data=request.data, partial=partial)
                if serializer.is_valid(raise_exception=True):
                    self.perform_update(serializer)
                    proceso.contador = proceso.contador - 1
                    proceso.save()
                    print("edito proceso contrato")
                    return Response(serializer.data, status=status.HTTP_200_OK)
                else:
                    return Response({'errors': serializer.errors})
            else:
                return Response({'msj': 'LLegaste al limite de tus modificaciones en el proceso'}, status=status.HTTP_205_RESET_CONTENT)
      
        except Exception as e:
            print(f"el error es: {e}")
            exc_type, exc_obj, exc_tb = sys.exc_info()
            logger.error(f"{datetime.now()} Ocurrió un error en el archivo {exc_tb.tb_frame.f_code.co_filename}, en el método {exc_tb.tb_frame.f_code.co_name}, en la línea {exc_tb.tb_lineno}:  {e}")
            return Response({'error': str(e)}, status= status.HTTP_400_BAD_REQUEST)
    
    def aprobar_contrato(self, request, *args, **kwargs):
        try:
            print("update status contrato")
            print("Request",request.data)
            instance = self.queryset.get(id = request.data["id"])
            print("mi id es: ",instance.id)
            print(instance.__dict__)
            #se utiliza el "get" en lugar del filter para obtener el objeto y no un queryset
            proceso = ProcesoContrato.objects.all().get(contrato_id = instance.id)
            print("proceso",proceso.__dict__)
            proceso.status_proceso = request.data["status"]
            proceso.save()
            return Response({'Exito': 'Se cambio el estatus a aprobado'}, status= status.HTTP_200_OK)
        except Exception as e:
            print(f"el error es: {e}")
            exc_type, exc_obj, exc_tb = sys.exc_info()
            logger.error(f"{datetime.now()} Ocurrió un error en el archivo {exc_tb.tb_frame.f_code.co_filename}, en el método {exc_tb.tb_frame.f_code.co_name}, en la línea {exc_tb.tb_lineno}:  {e}")
            return Response({'error': str(e)}, status= status.HTTP_400_BAD_REQUEST)
        
    def generar_pagare(self, request, *args, **kwargs):
        try:
            #activamos la libreri de locale para obtener el mes en español
            locale.setlocale(locale.LC_ALL,"es-ES")
            id_paq = request.data
            print("el id que llega", id_paq)
            info = self.queryset.filter(id = id_paq).first()
            print(info.__dict__)       
            # Definir la fecha inicial
            fecha_inicial = info.fecha_move_in
            print(fecha_inicial)
            #fecha_inicial = datetime(2024, 3, 20)
            #checar si cambiar el primer dia o algo asi
            # fecha inicial move in
            dia = fecha_inicial.day
            
            # Definir la duración en meses
            duracion_meses = info.duracion.split()
            duracion_meses = int(duracion_meses[0])
            print("duracion en meses",duracion_meses)
            # Calcular la fecha final
            fecha_final = fecha_inicial + relativedelta(months=duracion_meses)
            # Lista para almacenar las fechas iteradas (solo meses y años)
            fechas_iteradas = []
            # Iterar sobre todos los meses entre la fecha inicial y la fecha final
            while fecha_inicial < fecha_final:
                nombre_mes = fecha_inicial.strftime("%B")  # %B da el nombre completo del mes
                print("fecha",fecha_inicial.year)
                fechas_iteradas.append((nombre_mes.capitalize(),fecha_inicial.year))      
                fecha_inicial += relativedelta(months=1)
            
            print("fechas_iteradas",fechas_iteradas)
            # Imprimir la lista de fechas iteradas
            for month, year in fechas_iteradas:
                print(f"Año: {year}, Mes: {month}")
            
            #obtenermos la renta para pasarla a letra
            number = info.renta
            number = int(number)
            text_representation = num2words(number, lang='es')  # 'es' para español, puedes cambiarlo según el idioma deseado
            text_representation = text_representation.capitalize()
            
            context = {'info': info, 'dia':dia ,'lista_fechas':fechas_iteradas, 'text_representation':text_representation, 'duracion_meses':duracion_meses}
            
            template = 'home/pagare_fraterna.html'
            html_string = render_to_string(template, context)

            # Genera el PDF utilizando weasyprint
            pdf_file = HTML(string=html_string).write_pdf()

            # Devuelve el PDF como respuesta
            response = HttpResponse(content_type='application/pdf')
            response['Content-Disposition'] = 'attachment; filename="Pagare.pdf"'
            response.write(pdf_file)

            return HttpResponse(response, content_type='application/pdf')
    
        except Exception as e:
            print(f"el error es: {e}")
            exc_type, exc_obj, exc_tb = sys.exc_info()
            logger.error(f"{datetime.now()} Ocurrió un error en el archivo {exc_tb.tb_frame.f_code.co_filename}, en el método {exc_tb.tb_frame.f_code.co_name}, en la línea {exc_tb.tb_lineno}:  {e}")
            return Response({'error': str(e)}, status= status.HTTP_400_BAD_REQUEST)
    
    def generar_poliza(self, request, *args, **kwargs):
        try:
            print("Generar Poliza Fraterna")
            id_paq = request.data
            print("el id que llega", id_paq)
            info = self.queryset.filter(id = id_paq).first()
            print(info.__dict__)
            print()
            
            #vamos a genenrar el numero de contrato
            arrendatario = info.residente.nombre_arrendatario
            primera_letra = arrendatario[0].upper()  # Obtiene la primera letra
            ultima_letra = arrendatario[-1].upper()  # Obtiene la última letra

            year = info.fecha_celebracion.strftime("%g")
            month = info.fecha_celebracion.strftime("%m")
            
            nom_contrato = f"AFY{month}{year}CX51{info.id}CA{primera_letra}{ultima_letra}"  
            print("Nombre del contrato", nom_contrato)     
            #obtenemos renta y costo poliza para letra
            renta = int(info.renta)
            renta_texto = num2words(renta, lang='es').capitalize()
            
       
            context = {'info': info, 'renta_texto':renta_texto, 'nom_contrato':nom_contrato,}
            template = 'home/poliza_fraterna.html'
            html_string = render_to_string(template,context)

            # Genera el PDF utilizando weasyprint
            pdf_file = HTML(string=html_string).write_pdf()

            # Devuelve el PDF como respuesta
            response = HttpResponse(content_type='application/pdf')
            response['Content-Disposition'] = 'attachment; filename="Poliza.pdf"'
            response.write(pdf_file)
            print("TERMINANDO PROCESO CONTRATO")
            return HttpResponse(response, content_type='application/pdf')
        except Exception as e:
            print(f"el error es: {e}")
            exc_type, exc_obj, exc_tb = sys.exc_info()
            logger.error(f"{datetime.now()} Ocurrió un error en el archivo {exc_tb.tb_frame.f_code.co_filename}, en el método {exc_tb.tb_frame.f_code.co_name}, en la línea {exc_tb.tb_lineno}:  {e}")
            return Response({'error': str(e)}, status= status.HTTP_400_BAD_REQUEST)
    
    def generar_contrato(self, request, *args, **kwargs):
        try:
            print("Generar contrato Fraterna")
            id_paq = request.data
            print("el id que llega", id_paq)
            info = self.queryset.filter(id = id_paq).first()
            print(info.__dict__)       
            #obtenermos la renta para pasarla a letra
            habitantes = int(info.habitantes)
            habitantes_texto = num2words(habitantes, lang='es')  # 'es' para español, puedes cambiarlo según el idioma deseado
            #obtenemos renta y costo poliza para letra
            renta = int(info.renta)
            renta_texto = num2words(renta, lang='es').capitalize()
            
            #obtener la tipologia
            # Definir las opciones y sus correspondientes valores para la variable "plano"
            opciones = {
                'Loft': "https://arrendifystorage.s3.us-east-2.amazonaws.com/Recursos/Fraterna/loft.png",
                'Twin': "https://arrendifystorage.s3.us-east-2.amazonaws.com/Recursos/Fraterna/twin.png",
                'Double': "https://arrendifystorage.s3.us-east-2.amazonaws.com/Recursos/Fraterna/double.png",
                'Squad': "https://arrendifystorage.s3.us-east-2.amazonaws.com/Recursos/Fraterna/squad.png",
                'Master': "https://arrendifystorage.s3.us-east-2.amazonaws.com/Recursos/Fraterna/master.png",
                'Crew': "https://arrendifystorage.s3.us-east-2.amazonaws.com/Recursos/Fraterna/crew.png",
                'Party': "https://arrendifystorage.s3.us-east-2.amazonaws.com/Recursos/Fraterna/party.png"
            }
            
            inventario = {
                'Loft': "https://arrendifystorage.s3.us-east-2.amazonaws.com/Recursos/Fraterna/inventario/inventario_loft.jpg",
                'Twin': "https://arrendifystorage.s3.us-east-2.amazonaws.com/Recursos/Fraterna/inventario/inventario_twin.jpg",
                'Double': "https://arrendifystorage.s3.us-east-2.amazonaws.com/Recursos/Fraterna/inventario/inventario_double.jpg",
                'Squad': "https://arrendifystorage.s3.us-east-2.amazonaws.com/Recursos/Fraterna/inventario/inventario_squad.jpg",
                'Master': "https://arrendifystorage.s3.us-east-2.amazonaws.com/Recursos/Fraterna/inventario/inventario_master.jpg",
                'Crew': "https://arrendifystorage.s3.us-east-2.amazonaws.com/Recursos/Fraterna/inventario/inventario_crew.jpg",
                'Party': "https://arrendifystorage.s3.us-east-2.amazonaws.com/Recursos/Fraterna/inventario/inventario_party.jpg"
            }
            
            tipologia = info.tipologia
            if tipologia in opciones and tipologia in inventario:
                plano = opciones[tipologia]
                tabla_inventario = inventario[tipologia]
                print(f"Tu Tipologia es: {tipologia}, URL: {plano}")
                print(f"Tu Tipologia es: {tipologia}, Inventario: {tabla_inventario}")
            
            #obtener la url de el plano que sube fraterna
            plan_loc = f"https://arrendifystorage.s3.us-east-2.amazonaws.com/static/{info.plano_localizacion}"
           
            context = {'info': info, 'habitantes_texto':habitantes_texto, 'renta_texto':renta_texto, 'plano':plano, 'plan_loc':plan_loc, 'tabla_inventario':tabla_inventario}
            template = 'home/contrato_fraterna.html'
            html_string = render_to_string(template,context)

            # Genera el PDF utilizando weasyprint
            pdf_file = HTML(string=html_string).write_pdf()

            # Devuelve el PDF como respuesta
            response = HttpResponse(content_type='application/pdf')
            response['Content-Disposition'] = 'attachment; filename="Poliza.pdf"'
            response.write(pdf_file)
            print("TERMINANDO PROCESO CONTRATO")
            return HttpResponse(response, content_type='application/pdf')
        
        except Exception as e:
            print(f"el error es: {e}")
            exc_type, exc_obj, exc_tb = sys.exc_info()
            logger.error(f"{datetime.now()} Ocurrió un error en el archivo {exc_tb.tb_frame.f_code.co_filename}, en el método {exc_tb.tb_frame.f_code.co_name}, en la línea {exc_tb.tb_lineno}:  {e}")
            return Response({'error': str(e)}, status= status.HTTP_400_BAD_REQUEST) 
        
    def generar_comodato(self, request, *args, **kwargs):
        try:
            print("Generar comodato Fraterna")
            id_paq = request.data
            print("el id que llega", id_paq)
            info = self.queryset.filter(id = id_paq).first()
            print(info.__dict__)       
            #obtenermos la duracion para pasarla a letra
            duracion_meses = info.duracion.split()
            duracion_meses = int(duracion_meses[0])
            duracion_texto = num2words(duracion_meses, lang='es')  # 'es' para español, puedes cambiarlo según el idioma deseado
            #obtenemos renta y costo poliza para letra
            renta = int(info.renta)
            renta_texto = num2words(renta, lang='es').capitalize()
            
            #obtener la tipologia
            # Definir las opciones y sus correspondientes valores para la variable "plano"
            opciones = {
                'Loft': "https://arrendifystorage.s3.us-east-2.amazonaws.com/Recursos/Fraterna/loft.png",
                'Twin': "https://arrendifystorage.s3.us-east-2.amazonaws.com/Recursos/Fraterna/twin.png",
                'Double': "https://arrendifystorage.s3.us-east-2.amazonaws.com/Recursos/Fraterna/double.png",
                'Squad': "https://arrendifystorage.s3.us-east-2.amazonaws.com/Recursos/Fraterna/squad.png",
                'Master': "https://arrendifystorage.s3.us-east-2.amazonaws.com/Recursos/Fraterna/master.png",
                'Crew': "https://arrendifystorage.s3.us-east-2.amazonaws.com/Recursos/Fraterna/crew.png",
                'Party': "https://arrendifystorage.s3.us-east-2.amazonaws.com/Recursos/Fraterna/party.png"
            }
            
            inventario = {
                'Loft': "https://arrendifystorage.s3.us-east-2.amazonaws.com/Recursos/Fraterna/inventario/inventario_loft.jpg",
                'Twin': "https://arrendifystorage.s3.us-east-2.amazonaws.com/Recursos/Fraterna/inventario/inventario_twin.jpg",
                'Double': "https://arrendifystorage.s3.us-east-2.amazonaws.com/Recursos/Fraterna/inventario/inventario_double.jpg",
                'Squad': "https://arrendifystorage.s3.us-east-2.amazonaws.com/Recursos/Fraterna/inventario/inventario_squad.jpg",
                'Master': "https://arrendifystorage.s3.us-east-2.amazonaws.com/Recursos/Fraterna/inventario/inventario_master.jpg",
                'Crew': "https://arrendifystorage.s3.us-east-2.amazonaws.com/Recursos/Fraterna/inventario/inventario_crew.jpg",
                'Party': "https://arrendifystorage.s3.us-east-2.amazonaws.com/Recursos/Fraterna/inventario/inventario_party.jpg"
            }
            
            tipologia = info.tipologia
            if tipologia in opciones and tipologia in inventario:
                plano = opciones[tipologia]
                tabla_inventario = inventario[tipologia]
                print(f"Tu Tipologia es: {tipologia}, URL: {plano}")
                print(f"Tu Tipologia es: {tipologia}, Inventario: {tabla_inventario}")
            
            #obtener la url de el plano que sube fraterna
            plan_loc = f"https://arrendifystorage.s3.us-east-2.amazonaws.com/static/{info.plano_localizacion}"
           
            context = {'info': info, 'duracion_meses':duracion_meses, 'duracion_texto':duracion_texto, 'renta_texto':renta_texto, 'plano':plano, 'plan_loc':plan_loc, 'tabla_inventario':tabla_inventario}
            template = 'home/comodato_fraterna.html'
            html_string = render_to_string(template,context)

            # Genera el PDF utilizando weasyprint
            pdf_file = HTML(string=html_string).write_pdf()

            # Devuelve el PDF como respuesta
            response = HttpResponse(content_type='application/pdf')
            response['Content-Disposition'] = 'attachment; filename="Poliza.pdf"'
            response.write(pdf_file)
            print("TERMINANDO PROCESO CONTRATO")
            return HttpResponse(response, content_type='application/pdf')
        
        except Exception as e:
            print(f"el error es: {e}")
            exc_type, exc_obj, exc_tb = sys.exc_info()
            logger.error(f"{datetime.now()} Ocurrió un error en el archivo {exc_tb.tb_frame.f_code.co_filename}, en el método {exc_tb.tb_frame.f_code.co_name}, en la línea {exc_tb.tb_lineno}:  {e}")
            return Response({'error': str(e)}, status= status.HTTP_400_BAD_REQUEST) 
        
        