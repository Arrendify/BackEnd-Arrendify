from rest_framework.decorators import api_view
from rest_framework.response import Response
from rest_framework import viewsets
from rest_framework import status
from rest_framework.authentication import TokenAuthentication,SessionAuthentication
from rest_framework.permissions import IsAuthenticated, AllowAny
#nuevo modelo user
from ...home.models import Investigacion_Laboral,Investigacion_Inquilino,Investigacion_Judicial,Investigacion_Financiera
from ..views import *
from ..serializers import InvestigacionFinancieraSerializer,InvestigacionInquilinoSerializer,InvestigacionJudicialSerializer,InvestigacionLaboralSerializer,DocumentosLaboralSerializer
from ...accounts.models import CustomUser
User = CustomUser

#obtener Logs de errores
import logging
import sys
logger = logging.getLogger(__name__)

#enviar por correo
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.base import MIMEBase
from email import encoders
from smtplib import SMTPException
from django.core.files.base import ContentFile
from decouple import config

# Heath Check
from django.http import JsonResponse

#----------------------Investigacion Laboral-------------------------------------- 

class InvestigacionLaboralViewSet(viewsets.ViewSet):
    # Autenticación y permisos
    authentication_classes = [TokenAuthentication, SessionAuthentication]
    permission_classes = [IsAuthenticated]
    serializer_class = InvestigacionLaboralSerializer
    queryset = Investigacion_Laboral.objects.all()
    
    
    def list(self, request, *args, **kwargs):
        user_session = request.user
        try:    
            if request.method == 'GET':
                if user_session.is_staff:
                    snippets = Investigacion_Laboral.objects.all().order_by('-id')
                    
                    # Crear una copia de los datos serializados
                    serializer = InvestigacionLaboralSerializer(snippets, many=True)
                    serialized_data = serializer.data

                    # Agregar el campo 'is_staff'
                    for item in serialized_data:
                        item['is_staff'] = True

                    # Devolver la respuesta
                    return Response(serialized_data)
                
                    # Listar muchos a muchos
                    # Obtener todos las investigaciones del usuario actual
                investigacion_propia = Investigacion_Laboral.objects.all().filter(user_id = user_session)
                print(investigacion_propia)
   
                serializer = InvestigacionLaboralSerializer(snippets, many=True)
            
                return Response(serializer.data)
            
        except Exception as e:
            print(f"el error es: {e}")
            exc_type, exc_obj, exc_tb = sys.exc_info()
            logger.error(f"{datetime.now()} Ocurrió un error en el archivo {exc_tb.tb_frame.f_code.co_filename}, en el método {exc_tb.tb_frame.f_code.co_name}, en la línea {exc_tb.tb_lineno}:  {e}")
            return Response({'error': str(e)}, status=status.HTTP_400_BAD_REQUEST)
    
    def create(self, request, *args, **kwargs):
        try:
            data_documentos = {}
            print("entro a post")
            data = request.data  # Crea una copia de los datos          
            serializerlab = InvestigacionLaboralSerializer(data=data)# Crear el serializer con los datos enviados en la petición
            if serializerlab.is_valid():# Validar los datos antes de guardarlos
                documentos = ['cartalab1','cartalab2','cartalab3','cartalab4']
                print("antes de For:",data_documentos)
                for field in documentos:
                    print("campo",field)
                    if field in request.FILES:
                        data_documentos[field] = request.FILES[field]
                    else:
                        data_documentos[field] = None
                        
                print("aqui estan los documentos :D ", data_documentos)        
                prospecto = serializerlab.save(user = request.user)
                data_documentos["prospecto"] = prospecto.id
                
                print("serializer",data_documentos)
                documentos_serializer = DocumentosLaboralSerializer(data=data_documentos)
                documentos_serializer.is_valid()
                documentos_serializer.save(user = request.user)
                print("Guardado")
                # Guardar el objeto con el usuario autenticado
                return Response({'prospecto': serializerlab.data}, status = status.HTTP_201_CREATED)
                
            
            else:
                # Si la validación falla, devolver los errores
                return Response({'Error al guardar datos': serializerlab.errors}, status=status.HTTP_400_BAD_REQUEST)

        except Exception as e:
            # Captura general de errores
            exc_type, exc_obj, exc_tb = sys.exc_info()
            logger.error(f"{datetime.now()} Ocurrió un error en el archivo {exc_tb.tb_frame.f_code.co_filename}, "
                         f"en el método {exc_tb.tb_frame.f_code.co_name}, en la línea {exc_tb.tb_lineno}: {e}")
            return Response({'error': str(e)}, status=status.HTTP_400_BAD_REQUEST)
        

    def investigacion_laboral (self, request, *args, **kwargs):
        print("Investigacion Laboral")
        try:
                print("entrando en Aprobar prospecto")
                #Consulata para obtener el inquilino y establecemos fecha de hoy
                today = date.today().strftime('%d/%m/%Y')
                req_dat = request.data
                info = Investigacion_Laboral.objects.filter(id = req_dat["id"]).first()
                print("soy INFO",info.__dict__)         
                
                print("")
                print("soy la info del",info.nombre_completo)       

                requisitos = ['referencia1', 'referencia2', 'referencia3'] # una lista para verificar las referencias 1,2 y 3
                presentes = [req for req in requisitos if req in request.data and request.data[req]]
                print("Referencias presentes: ",presentes)
                if len(presentes) == 3:
                    referencias = "En consideración a lo referido por las referencias podemos constatar que la informacion brindada por el prospecto al inicio del tramite es verídica, lo cual nos permite estimar que cuenta con buenos comentarios hacia su persona."
                elif len(presentes) > 0:
                    referencias = "En cuanto a la recolección de información por parte de las referencias se nos imposibilita aseverar la cabalidad de la persona a investigar referente a su ámbito social, toda vez que no se logró entablar comunicación con alguna(s) referencias proporcionadas, por lo tanto, no podemos corroborar por completo la veracidad de la información proporcionada en la solicitud de arrendamiento. "
                else:
                    referencias = "En cuanto a la recolección de información por parte de las referencias se nos imposibilita aseverar la cabalidad de la persona a investigar referente a su ámbito social, toda vez que no se logró entablar comunicación con ninguna de las referencias proporcionadas, por lo tanto, no podemos corroborar la veracidad de la información proporcionada en la solicitud de arrendamiento. "
                
                opciones = {
                    'Excelente': "https://arrendifystorage.s3.us-east-2.amazonaws.com/Recursos/medidores/medidor_excelente.png",
                    'Bueno': "https://arrendifystorage.s3.us-east-2.amazonaws.com/Recursos/medidores/medidor_bueno.png",
                    'Regular': "https://arrendifystorage.s3.us-east-2.amazonaws.com/Recursos/medidores/medidor_regular.png",
                    'Malo': "https://arrendifystorage.s3.us-east-2.amazonaws.com/Recursos/medidores/medidor_malo.png"
                }
                
                tipo_score_ingreso = req_dat["tipo_score_ingreso"]
                tipo_score_pp = req_dat["tipo_score_pp"]
                tipo_score_credito = req_dat["tipo_score_credito"]
                
                if tipo_score_ingreso and tipo_score_pp and tipo_score_credito in opciones:
                    tsi = opciones[tipo_score_ingreso]
                    tspp = opciones[tipo_score_pp]
                    tsc = opciones[tipo_score_credito]
                    print(f"Tu Tipo de score ingresos es: {tipo_score_ingreso}, URL: {tsi}")
                    print(f"Tu Tipo de score de pagos puntuales es: {tipo_score_pp}, URL: {tspp}")
                    print(f"Tu Tipo de score de credito es: {tipo_score_credito}, URL: {tsc}")

                
                #Dar conclusion dinamica
                antecedentes = request.data.get('antecedentes') # Obtenemos todos los antecedentes del prospecto
                print("ANTECEDENTES",antecedentes)
                if antecedentes:
                    # del antecedentes["civil_mercantil_demandado"] 
                    print("tienes antecedences, vamos a ver si es civil o familiar",antecedentes)
                    if antecedentes.get("civil_mercantil_demandado") and len(antecedentes) == 1: #tiene antecedentes de civil o de familiar? los excentamos si no delincuente
                        print("Tiene antecedentes civiles o familiares")
                        print("Checamos el historial")
                        #evaluar el historial crediticio  
                        
                        if tipo_score_pp == "Malo" or tipo_score_ingreso == "Malo":
                            print("rechazado")
                            conclusion = "Lamentamos informar que el candidato ha sido rechazado tras el análisis de riesgo realizado por ARRENDIFY S.A.P.I. de C.V. Los resultados de la investigación determinan que es inseguro arrendar el inmueble al prospecto debido a los aspectos que se han detallado en lo expuesto anteriormente respecto a:"    
                            motivo = "1.- Buro: Se cuenta con un buro en con atrasos y/o adeudos, estos datos se detallan en el apartado correspondiente."
                        
                        elif tipo_score_pp == "Excelente" and tipo_score_ingreso == "Excelente" or tipo_score_pp == "Excelente" and tipo_score_ingreso == "Bueno" or tipo_score_pp == "Bueno" and tipo_score_ingreso == "Excelente":
                            print("aprobado")
                            conclusion = f"Nos complace informar que el prospecto {info.nombre_completo} ha sido aprobado tras una rigurosa investigación llevada a cabo por el equipo legal de ARRENDIFY S.A.P.I. de C.V. Los resultados obtenidos en todos los parámetros evaluados se encuentran dentro del rango de tolerancia establecido por los criterios de evaluación de la empresa. Esto confirma que el candidato cumple con los requisitos y estándares exigidos, validando así su idoneidad para el arrendamiento en cuestión."
                            motivo = "No hay motivo de rechazo"
                        
                        elif tipo_score_pp != "Malo" and tipo_score_ingreso != "Malo":
                            print("a considerar")
                            conclusion = "Nos complace informar que el candidato ha sido aprobado tras una rigurosa investigación llevada a cabo por ARRENDIFY S.A.P.I. de C.V. Los resultados obtenidos en todos los parámetros evaluados se encuentran dentro del rango de tolerancia establecido por los criterios de evaluación de la empresa, confirmando así que el candidato cumple con los requisitos exigidos. \n \n No obstante, es importante considerar que la investigación ha revelado ciertos puntos que deben tomarse en cuenta, los cuales se detallado en lo expuesto anteriormente respecto a:"
                            motivo = "1.- Antecedentes: Se cuenta con demanda en materia civil o familiar.\n2.- Buro: Historial crediticio con algunas áreas que podrían mejorarse."
                        
                    elif antecedentes and tipo_score_pp == "Malo" or antecedentes and tipo_score_ingreso == "Malo":
                            print("rechazado")
                            conclusion = "Lamentamos informar que el candidato ha sido rechazado tras el análisis de riesgo realizado por ARRENDIFY S.A.P.I. de C.V. Los resultados de la investigación determinan que es inseguro arrendar el inmueble al prospecto debido a los aspectos que se han detallado en lo expuesto anteriormente respecto a:"    
                            motivo = "1.- Buro: Se cuenta con un buro en con atrasos y/o adeudos, estos datos se detallan en el apartado correspondiente.\n2.- Antecedentes: Se cuenta con antecedentes legales, que se detallan en el apartado correspondiente."    
                            
                    else:
                        print("eres un delincuente")
                        conclusion = "Lamentamos informar que el candidato ha sido rechazado tras el análisis de riesgo realizado por ARRENDIFY S.A.P.I. de C.V. Los resultados de la investigación determinan que es inseguro arrendar el inmueble al prospecto debido a los aspectos que se han detallado en lo expuesto anteriormente respecto a:"    
                        motivo = "1.- Antecedentes: Se cuenta con antecedentes legales, que se detallan en el apartado correspondiente."
                else: #No tiene Antecedentes
                    
                    #evaluar el historial crediticio  
                    if tipo_score_pp == "Malo" or tipo_score_ingreso == "Malo":
                        print("rechazado")
                        conclusion = "Lamentamos informar que el candidato ha sido rechazado tras el análisis de riesgo realizado por ARRENDIFY S.A.P.I. de C.V. Los resultados de la investigación determinan que es inseguro arrendar el inmueble al prospecto debido a los aspectos que se han detallado en lo expuesto anteriormente respecto a:"    
                        motivo = "1.- Buro: Se cuenta con un buro en con atrasos y/o adeudos, estos datos se detallan en el apartado correspondiente."
                    
                    elif tipo_score_pp == "Excelente" and tipo_score_ingreso == "Excelente" or tipo_score_pp == "Excelente" and tipo_score_ingreso == "Bueno" or tipo_score_pp == "Bueno" and tipo_score_ingreso == "Excelente":
                        print("aprobado")
                        conclusion = f"Nos complace informar que el prospecto {info.nombre_completo} ha sido aprobado tras una rigurosa investigación llevada a cabo por el equipo legal de ARRENDIFY S.A.P.I. de C.V. Los resultados obtenidos en todos los parámetros evaluados se encuentran dentro del rango de tolerancia establecido por los criterios de evaluación de la empresa. Esto confirma que el candidato cumple con los requisitos y estándares exigidos, validando así su idoneidad para el arrendamiento en cuestión."
                        motivo = "hola"   
                    
                    elif tipo_score_pp != "Malo" and tipo_score_ingreso != "Malo":
                        print("a considerar")
                        conclusion = "Nos complace informar que el candidato ha sido aprobado tras una rigurosa investigación llevada a cabo por ARRENDIFY S.A.P.I. de C.V. Los resultados obtenidos en todos los parámetros evaluados se encuentran dentro del rango de tolerancia establecido por los criterios de evaluación de la empresa, confirmando así que el candidato cumple con los requisitos exigidos. \n \n No obstante, es importante considerar que la investigación ha revelado ciertos puntos que deben tomarse en cuenta, los cuales se detallado en lo expuesto anteriormente respecto a:"
                        motivo = "1.- Buro: Historial crediticio con algunas áreas que podrían mejorarse."
                        
                context = {'info': info, "fecha_consulta":today, 'datos':req_dat, 'tsi':tsi, 'tspp':tspp, 'tsc':tsc, 
                        'referencias':referencias, 'antecedentes':antecedentes, 'conclusion':conclusion, 'motivo':motivo}
            
                
                template = 'home/report_laboral.html'
                html_string = render_to_string(template, context)

                # Genera el PDF utilizando weasyprint
                print("Generando el pdf")
                pdf_file = HTML(string=html_string).write_pdf()
                #aqui hacia abajo es para enviar por email
                # archivo = ContentFile(pdf_file, name='aprobado.pdf') # lo guarda como content raw para enviar el correo
            
                # print("antes de enviar_archivo",context)
                # self.enviar_archivo(archivo, context["info"], context["status"])
                
            # Aprobar o desaprobar
                if info.status == "Pendiente":  
                    print("status de inquilino",info.status)
                    info.status = "Revisado"
                    info.save()
                    print("status cambiado",info.status)
                    info.save()
                
                print("PDF ENVIADO")
                
                # return Response({'mensaje': "Todo salio bien, pdf enviado"}, status = "200")
            
                # de aqui hacia abajo Devuelve esl PDF como respuesta
                response = HttpResponse(content_type='application/pdf')
                response['Content-Disposition'] = 'attachment; filename="Pagare.pdf"'
                response.write(pdf_file)
                print("Finalizamos el proceso de aprobado") 
                return HttpResponse(response, content_type='application/pdf')
        
        except Exception as e:
                print(f"el error es: {e}")
                exc_type, exc_obj, exc_tb = sys.exc_info()
                logger.error(f"{datetime.now()} Ocurrió un error en el archivo {exc_tb.tb_frame.f_code.co_filename}, en el método {exc_tb.tb_frame.f_code.co_name}, en la línea {exc_tb.tb_lineno}:  {e}")
                return Response({'error': str(e)}, status = "404") 

#----------------------Investigacion Inquilino--------------------------------------     
        
class InvestigacionInquilinoViewSet(viewsets.ViewSet):
    # Autenticación y permisos
    authentication_classes = [TokenAuthentication, SessionAuthentication]
    permission_classes = [IsAuthenticated]
    serializer_class = InvestigacionInquilinoSerializer
    queryset = Investigacion_Inquilino.objects.all()
    
    def list(self, request, *args, **kwargs):
        user_session = request.user
        try:    
            if request.method == 'GET':
                if user_session.is_staff:
                    snippets = Investigacion_Inquilino.objects.all().order_by('-id')
                    
                    # Crear una copia de los datos serializados
                    serializer = InvestigacionInquilinoSerializer(snippets, many=True)
                    serialized_data = serializer.data

                    # Agregar el campo 'is_staff'
                    for item in serialized_data:
                        item['is_staff'] = True

                    # Devolver la respuesta
                    return Response(serialized_data)
                
                    # Listar muchos a muchos
                    # Obtener todos las investigaciones del usuario actual
                investigacion_propia = Investigacion_Inquilino.objects.all().filter(user_id = user_session)
                print(investigacion_propia)
   
                serializer = InvestigacionInquilinoSerializer(snippets, many=True)
            
                return Response(serializer.data)
            
        except Exception as e:
            print(f"el error es: {e}")
            exc_type, exc_obj, exc_tb = sys.exc_info()
            logger.error(f"{datetime.now()} Ocurrió un error en el archivo {exc_tb.tb_frame.f_code.co_filename}, en el método {exc_tb.tb_frame.f_code.co_name}, en la línea {exc_tb.tb_lineno}:  {e}")
            return Response({'error': str(e)}, status=status.HTTP_400_BAD_REQUEST)
    
    
    def create(self, request, *args, **kwargs):
        try:
            user_session = request.user  # Obtener el usuario autenticado
            print("entro a post")
            # Crea un nuevo diccionario con los datos de la solicitud y agrega el campo 'user'
            data = request.data.copy()  # Crea una copia de los datos
            data['user'] = user_session.id  # Agregar el ID del usuario al diccionario
            
            # Crear el serializer con los datos enviados en la petición
            serializerinq = InvestigacionInquilinoSerializer(data=data)
            print("Este es el Serializer: ",serializerinq)
            
            if serializerinq.is_valid():  # Validar los datos antes de guardarlos
                serializerinq.save(user=user_session)
                print("Guardado")
                # Guardar el objeto con el usuario autenticado
                return Response(serializerinq.data, status=status.HTTP_201_CREATED)
                
            
            else:
                # Si la validación falla, devolver los errores
                return Response(serializerinq.errors, status=status.HTTP_400_BAD_REQUEST)

        except Exception as e:
            # Captura general de errores
            print(f"error: {e}")
            exc_type, exc_obj, exc_tb = sys.exc_info()
            logger.error(f"{datetime.now()} Ocurrió un error en el archivo {exc_tb.tb_frame.f_code.co_filename}, "
                         f"en el método {exc_tb.tb_frame.f_code.co_name}, en la línea {exc_tb.tb_lineno}: {e}")
            return Response({'error': str(e)}, status=status.HTTP_400_BAD_REQUEST)
        
    def enviar_archivo(self, archivo, info, estatus):

        print("soy pdf content",archivo)
        print("soy info", info)
        print("soy status",estatus)
        print("soy info de investigacion",info.__dict__)
        print("info id",info.user_id)
   
        # Configura los detalles del correo electrónico
        try:
            remitente = 'notificaciones_arrendify@outlook.com'
            destinatario = info.email
            print("destinatario pasado")
            pdf_html = contenido_pdf_aprobado(info,estatus)
            print("destinatario normalito",destinatario)
            
            #hacemos una lista destinatarios para enviar el correo
            Destino=['desarrolloarrendify@gmail.com',f'{destinatario}']
            asunto = f"Resultado Investigación Prospecto {info.nombre_completo}"
            
            # Crea un objeto MIMEMultipart para el correo electrónico
            msg = MIMEMultipart()
            msg['From'] = remitente
            msg['To'] = ','.join(Destino)
            msg['Subject'] = asunto
            print("paso objeto mime")
            
            #Evalua si tiene este atributo
            # if hasattr(info, 'fiador'):
            #     print("SOY info.fiador",info.fiador)
            
            # Adjuntar el contenido HTML al mensaje
            msg.attach(MIMEText(pdf_html, 'html'))
            print("pase el msg attach 1")
            # Adjunta el PDF al correo electrónico
            pdf_part = MIMEBase('application', 'octet-stream')
            pdf_part.set_payload(archivo.read())  # Lee los bytes del archivo
            encoders.encode_base64(pdf_part)
            pdf_part.add_header('Content-Disposition', 'attachment', filename='Reporte_de_investigación.pdf')
            msg.attach(pdf_part)
            print("pase el msg attach 2")
            
            # Establece la conexión SMTP y envía el correo electrónico
            smtp_server = 'smtp.office365.com'
            smtp_port = 587
            smtp_username = config('smtp_u')
            smtp_password = config('smtp_pw')
            with smtplib.SMTP(smtp_server, smtp_port) as server:   #Crea una instancia del objeto SMTP proporcionando el servidor SMTP y el puerto correspondiente 
                server.starttls() # Inicia una conexión segura (TLS) con el servidor SMTP
                print("tls")
                server.login(smtp_username, smtp_password) # Inicia sesión en el servidor SMTP utilizando el nombre de usuario y la contraseña proporcionados. 
                print("login")
                server.sendmail(remitente, Destino, msg.as_string()) # Envía el correo electrónico utilizando el método sendmail del objeto SMTP.
                print("sendmail")
            return Response({'message': 'Correo electrónico enviado correctamente.'})
        except SMTPException as e:
            print("Error al enviar el correo electrónico:", str(e))
            return Response({'message': 'Error al enviar el correo electrónico.'})
        
        
    def investigacion_inquilino(self, request, *args, **kwargs):
        try:
            print("entrando en Aprobar prospecto")
            #Consulta para obtener el inquilino y establecemos fecha de hoy
            today = date.today().strftime('%d/%m/%Y')
            req_dat = request.data
            info = Investigacion_Inquilino.objects.filter(id = req_dat["id"]).first()
            print("soy INFO",info.__dict__)          
            
            aval = info.nombre_completo_fiador
            redes_negativo = req_dat.get("redes_negativo")
            print("request.data",req_dat)
            print("el id que llega", req_dat["id"])
            print("")
            print("soy la info del",info.nombre_completo)       
            print(info.__dict__)
            print("")                                     
            print("")
            print("redes negativo", redes_negativo)            
            print("")
            
            requisitos = ['referencia1', 'referencia2', 'referencia3'] # una lista para verificar las referencias 1,2 y 3
            presentes = [req for req in requisitos if req in request.data and request.data[req]]
            print("Referencias presentes: ",presentes)
            if len(presentes) == 3:
                referencias = "En consideración a lo referido por las referencias podemos constatar que la informacion brindada por el prospecto al inicio del tramite es verídica, lo cual nos permite estimar que cuenta con buenos comentarios hacia su persona."
            elif len(presentes) > 0:
                referencias = "En cuanto a la recolección de información por parte de las referencias se nos imposibilita aseverar la cabalidad de la persona a investigar referente a su ámbito social, toda vez que no se logró entablar comunicación con alguna(s) referencias proporcionadas, por lo tanto, no podemos corroborar por completo la veracidad de la información proporcionada en la solicitud de arrendamiento. "
            else:
                referencias = "En cuanto a la recolección de información por parte de las referencias se nos imposibilita aseverar la cabalidad de la persona a investigar referente a su ámbito social, toda vez que no se logró entablar comunicación con ninguna de las referencias proporcionadas, por lo tanto, no podemos corroborar la veracidad de la información proporcionada en la solicitud de arrendamiento. "
            
            #comentarios de redes para walden
            if redes_negativo:
                redes_negativo = dict(redes_negativo)
                #inicializamos la lista 
                redes_comentarios = []
                #establecemos las frases
                conductas = {
                'conducta_violenta': "Conducta violenta o agresiva: Publicaciones que muestran armas de fuego u otros objetos peligrosos.",
                'conducta_discriminatoria': "Conducta discriminatoria o racista: Comentarios, imágenes o memes que promueven el racismo, sexismo, homofobia, transfobia u otro tipo de discriminación.",
                'contenido_ofensivo_odio': "Contenido ofensivo o de odio: Publicaciones que contienen discursos de odio contra diversos grupos étnicos, religiosos, de orientación sexual, género, etc",
                'bullying_acoso': "Bullying o acoso: Participación en o incitación al acoso, ya sea ciberacoso o en la vida real.",
                'contenido_inapropiado': "Contenido inapropiado o explícito: Publicaciones de contenido sexual explícito o inapropiado.",
                'desinformacion_teoria': "Desinformación y teorías conspirativas: Difusión de información falsa o engañosa, así como la promoción de teorías conspirativas sin fundamento que puedan poner en peligro la tranquilidad y orden dentro de la comunidad.",
                'lenguaje_vulgar': "Lenguaje vulgar o inapropiado: Uso excesivo de lenguaje vulgar o soez en sus publicaciones.",
                'contenido_poco_profesional': "Conducta poco profesional: Publicaciones que muestran comportamientos inapropiados en contextos profesionales.",
                'falta_integridad': "Falta de integridad: Inconsistencias en la información compartida en diferentes plataformas, o indicios de comportamientos engañosos o fraudulentos.",
                'divulgacion_info': "Divulgación de información confidencial: Publicaciones que revelan información privada o confidencial de empresas, clientes o individuos.",
                'exceso_negatividad': "Exceso de negatividad: Publicaciones predominantemente negativas o quejumbrosas.",
                'falta_respeto_priv': "Falta de respeto hacia la privacidad: Compartir información privada de otras personas sin su consentimiento.",
                'ausencia_diversidad': "Ausencia de diversidad y tolerancia: Falta de representación de diversas perspectivas y falta de respeto por la diversidad en sus publicaciones."
                }
                # Bucle para generar las frases basadas en los valores de redes_negativo
                for clave, valor in redes_negativo.items(): #hacemos un for basado en la clave valor del dicciones redes_negativo en el .items al ser un diccionario
                    if valor == "Si" and clave in conductas:
                        frase = conductas[clave]
                        #lo agregamos a la lista redes_comentarios
                        redes_comentarios.append(frase)
                        print("clave:", clave)
                        print("frase:", frase)
                        print("lista finalizada:", redes_comentarios)
                    elif valor == "Si" and clave not in conductas:
                        print(f"No hay una frase definida para la clave: {clave}")
            else:
                redes_comentarios = "no tengo datos"
                print("redes coments",redes_comentarios)
        
            #opciones para el score interno de nosotros
            opciones = {
                'Excelente': "https://arrendifystorage.s3.us-east-2.amazonaws.com/Recursos/medidores/medidor_excelente.png",
                'Bueno': "https://arrendifystorage.s3.us-east-2.amazonaws.com/Recursos/medidores/medidor_bueno.png",
                'Regular': "https://arrendifystorage.s3.us-east-2.amazonaws.com/Recursos/medidores/medidor_regular.png",
                'Malo': "https://arrendifystorage.s3.us-east-2.amazonaws.com/Recursos/medidores/medidor_malo.png"
            }
            
            tipo_score_ingreso = req_dat["tipo_score_ingreso"]
            tipo_score_pp = req_dat["tipo_score_pp"]
            tipo_score_credito = req_dat["tipo_score_credito"]
            
            if tipo_score_ingreso and tipo_score_pp and tipo_score_credito in opciones:
                tsi = opciones[tipo_score_ingreso]
                tspp = opciones[tipo_score_pp]
                tsc = opciones[tipo_score_credito]
                print(f"Tu Tipo de score ingresos es: {tipo_score_ingreso}, URL: {tsi}")
                print(f"Tu Tipo de score de pagos puntuales es: {tipo_score_pp}, URL: {tspp}")
                print(f"Tu Tipo de score de credito es: {tipo_score_credito}, URL: {tsc}")
            
            #evaluar el historial crediticio
            # if tipo_score_pp == "Excelente" and tipo_score_ingreso == "Excelente":
            #     print("aprobado")
            # elif tipo_score_pp != "Malo" and tipo_score_ingreso != "Excelente":
            #     print("a considerar")
            # else:
            #     print("rechazado")
            
            
            
            #evaluar el historial crediticio antes para no hacerlo 2 veces
            # if tipo_score_pp == "Excelente" and tipo_score_ingreso == "Excelente":
            #         print("aprobado")
            #         status = "Aprobado"
            #         conclusion = f"Nos complace informar que el prospecto {info.inquilino.nombre} {info.inquilino.apellido} {info.inquilino.apellido1} ha sido aprobado tras una rigurosa investigación llevada a cabo por el equipo legal de ARRENDIFY S.A.P.I. de C.V. Los resultados obtenidos en todos los parámetros evaluados se encuentran dentro del rango de tolerancia establecido por los criterios de evaluación de la empresa. Esto confirma que el candidato cumple con los requisitos y estándares exigidos, validando así su idoneidad para el arrendamiento en cuestión."
            
            # elif tipo_score_pp != "Malo" and tipo_score_ingreso != "Excelente":
            #     print("a considerar")
            #     status = "A considerar"
            #     conclusion = ""
                
            # else:
            #     print("rechazado") 
               
               
            #Dar conclusion dinamica
            antecedentes = request.data.get('antecedentes') # Obtenemos todos los antecedentes del prospecto
            print("ANTECEDENTES",antecedentes)
            if antecedentes:
                # del antecedentes["civil_mercantil_demandado"] 
                print("tienes antecedences, vamos a ver si es civil o familiar",antecedentes)
                if antecedentes.get("civil_mercantil_demandado") and len(antecedentes) == 1: #tiene antecedentes de civil o de familiar? los excentamos si no delincuente
                    print("Tiene antecedentes civiles o familiares")
                    print("Checamos el historial")
                    #evaluar el historial crediticio  
                    
                    if tipo_score_pp == "Malo" or tipo_score_ingreso == "Malo":
                        print("rechazado")
                        conclusion = "Lamentamos informar que el candidato ha sido rechazado tras el análisis de riesgo realizado por ARRENDIFY S.A.P.I. de C.V. Los resultados de la investigación determinan que es inseguro arrendar el inmueble al prospecto debido a los aspectos que se han detallado en lo expuesto anteriormente respecto a:"    
                        status = "Declinado"
                        motivo = "1.- Buro: Se cuenta con un buro en con atrasos y/o adeudos, estos datos se detallan en el apartado correspondiente."
                    
                    elif tipo_score_pp == "Excelente" and tipo_score_ingreso == "Excelente" or tipo_score_pp == "Excelente" and tipo_score_ingreso == "Bueno" or tipo_score_pp == "Bueno" and tipo_score_ingreso == "Excelente":
                        print("aprobado")
                        conclusion = f"Nos complace informar que el prospecto {info.nombre_completo} ha sido aprobado tras una rigurosa investigación llevada a cabo por el equipo legal de ARRENDIFY S.A.P.I. de C.V. Los resultados obtenidos en todos los parámetros evaluados se encuentran dentro del rango de tolerancia establecido por los criterios de evaluación de la empresa. Esto confirma que el candidato cumple con los requisitos y estándares exigidos, validando así su idoneidad para el arrendamiento en cuestión."
                        status = "Aprobado"
                        motivo = "No hay motivo de rechazo"
                    
                    elif tipo_score_pp != "Malo" and tipo_score_ingreso != "Malo":
                        print("a considerar")
                        conclusion = "Nos complace informar que el candidato ha sido aprobado tras una rigurosa investigación llevada a cabo por ARRENDIFY S.A.P.I. de C.V. Los resultados obtenidos en todos los parámetros evaluados se encuentran dentro del rango de tolerancia establecido por los criterios de evaluación de la empresa, confirmando así que el candidato cumple con los requisitos exigidos. \n \n No obstante, es importante considerar que la investigación ha revelado ciertos puntos que deben tomarse en cuenta, los cuales se detallado en lo expuesto anteriormente respecto a:"
                        status = "Aprobado_pe"
                        motivo = "1.- Antecedentes: Se cuenta con demanda en materia civil o familiar.\n2.- Buro: Historial crediticio con algunas áreas que podrían mejorarse."
                    
                elif antecedentes and tipo_score_pp == "Malo" or antecedentes and tipo_score_ingreso == "Malo":
                        print("rechazado")
                        conclusion = "Lamentamos informar que el candidato ha sido rechazado tras el análisis de riesgo realizado por ARRENDIFY S.A.P.I. de C.V. Los resultados de la investigación determinan que es inseguro arrendar el inmueble al prospecto debido a los aspectos que se han detallado en lo expuesto anteriormente respecto a:"    
                        status = "Declinado"
                        motivo = "1.- Buro: Se cuenta con un buro en con atrasos y/o adeudos, estos datos se detallan en el apartado correspondiente.\n2.- Antecedentes: Se cuenta con antecedentes legales, que se detallan en el apartado correspondiente."    
                        
                else:
                    print("eres un delincuente")
                    conclusion = "Lamentamos informar que el candidato ha sido rechazado tras el análisis de riesgo realizado por ARRENDIFY S.A.P.I. de C.V. Los resultados de la investigación determinan que es inseguro arrendar el inmueble al prospecto debido a los aspectos que se han detallado en lo expuesto anteriormente respecto a:"    
                    status = "Declinado"
                    motivo = "1.- Antecedentes: Se cuenta con antecedentes legales, que se detallan en el apartado correspondiente."
            else: #No tiene Antecedentes
                
                #evaluar el historial crediticio  
                if tipo_score_pp == "Malo" or tipo_score_ingreso == "Malo":
                    print("rechazado")
                    conclusion = "Lamentamos informar que el candidato ha sido rechazado tras el análisis de riesgo realizado por ARRENDIFY S.A.P.I. de C.V. Los resultados de la investigación determinan que es inseguro arrendar el inmueble al prospecto debido a los aspectos que se han detallado en lo expuesto anteriormente respecto a:"    
                    status = "Declinado"
                    motivo = "1.- Buro: Se cuenta con un buro en con atrasos y/o adeudos, estos datos se detallan en el apartado correspondiente."
                
                elif tipo_score_pp == "Excelente" and tipo_score_ingreso == "Excelente" or tipo_score_pp == "Excelente" and tipo_score_ingreso == "Bueno" or tipo_score_pp == "Bueno" and tipo_score_ingreso == "Excelente":
                    print("aprobado")
                    conclusion = f"Nos complace informar que el prospecto {info.nombre_completo} ha sido aprobado tras una rigurosa investigación llevada a cabo por el equipo legal de ARRENDIFY S.A.P.I. de C.V. Los resultados obtenidos en todos los parámetros evaluados se encuentran dentro del rango de tolerancia establecido por los criterios de evaluación de la empresa. Esto confirma que el candidato cumple con los requisitos y estándares exigidos, validando así su idoneidad para el arrendamiento en cuestión."
                    status = "Aprobado"
                    motivo = "hola"   
                
                elif tipo_score_pp != "Malo" and tipo_score_ingreso != "Malo":
                    print("a considerar")
                    conclusion = "Nos complace informar que el candidato ha sido aprobado tras una rigurosa investigación llevada a cabo por ARRENDIFY S.A.P.I. de C.V. Los resultados obtenidos en todos los parámetros evaluados se encuentran dentro del rango de tolerancia establecido por los criterios de evaluación de la empresa, confirmando así que el candidato cumple con los requisitos exigidos. \n \n No obstante, es importante considerar que la investigación ha revelado ciertos puntos que deben tomarse en cuenta, los cuales se detallado en lo expuesto anteriormente respecto a:"
                    status = "Aprobado_pe"
                    motivo = "1.- Buro: Historial crediticio con algunas áreas que podrían mejorarse."
                
                 
                    
            context = {'info': info, 'aval': aval, "fecha_consulta":today, 'datos':req_dat, 'tsi':tsi, 'tspp':tspp, 'tsc':tsc, 
                       "redes_comentarios":redes_comentarios, 'referencias':referencias, 'antecedentes':antecedentes,'status':status, 'conclusion':conclusion, 'motivo':motivo}
            
            template = 'home/report_inquilino.html'
            html_string = render_to_string(template, context)

            # Genera el PDF utilizando weasyprint
            print("Generando el pdf")
            pdf_file = HTML(string=html_string).write_pdf()
            #aqui hacia abajo es para enviar por email
            # archivo = ContentFile(pdf_file, name='aprobado.pdf') # lo guarda como content raw para enviar el correo
        
            # print("antes de enviar_archivo",context)
            # self.enviar_archivo(archivo, context["info"], context["status"])
            
            # # Aprobar o desaprobar
            if status == "Aprobado_pe" or status == "Aprobado":  
                 print("status de inquilino",info.status)
                 info.status = "Aprobado"
                 info.save()
                 print("status cambiado",info.status)
                 info.save()

            else:
                 print("status de inquilino",info.status)
                 info.status = "Rechazado"
                 info.save()
            
            # print("PDF ENVIADO")
            
            # return Response({'mensaje': "Todo salio bien, pdf enviado"}, status = "200")
           
            # de aqui hacia abajo Devuelve esl PDF como respuesta
            response = HttpResponse(content_type='application/pdf')
            response['Content-Disposition'] = 'attachment; filename="Pagare.pdf"'
            response.write(pdf_file)
            print("Finalizamos el proceso de aprobado") 
            return HttpResponse(response, content_type='application/pdf')
        
        except Exception as e:
            print(f"el error es: {e}")
            exc_type, exc_obj, exc_tb = sys.exc_info()
            logger.error(f"{datetime.now()} Ocurrió un error en el archivo {exc_tb.tb_frame.f_code.co_filename}, en el método {exc_tb.tb_frame.f_code.co_name}, en la línea {exc_tb.tb_lineno}:  {e}")
            return Response({'error': str(e)}, status = "404") 



class InvestigacionFinancieraViewSet(viewsets.ViewSet):

    def list(self, request, *args, **kwargs):
            user_session = request.user
            try:    
                if request.method == 'GET':
                    if user_session.is_staff:
                        snippets = Investigacion_Financiera.objects.all().order_by('-id')
                        
                        # Crear una copia de los datos serializados
                        serializer = InvestigacionFinancieraSerializer(snippets, many=True)
                        serialized_data = serializer.data

                        # Agregar el campo 'is_staff'
                        for item in serialized_data:
                            item['is_staff'] = True

                        # Devolver la respuesta
                        return Response(serialized_data)
                    
                        # Listar muchos a muchos
                        # Obtener todos las investigaciones del usuario actual
                    investigacion_propia = Investigacion_Financiera.objects.all().filter(user_id = user_session)
                    print(investigacion_propia)
    
                    serializer = InvestigacionFinancieraSerializer(snippets, many=True)
                
                    return Response(serializer.data)
                
            except Exception as e:
                print(f"el error es: {e}")
                exc_type, exc_obj, exc_tb = sys.exc_info()
                logger.error(f"{datetime.now()} Ocurrió un error en el archivo {exc_tb.tb_frame.f_code.co_filename}, en el método {exc_tb.tb_frame.f_code.co_name}, en la línea {exc_tb.tb_lineno}:  {e}")
                return Response({'error': str(e)}, status=status.HTTP_400_BAD_REQUEST)
    
    
    def create(self, request, *args, **kwargs):
        try:
            data_documentos = {}
            data = request.data  # Crea una copia de los datos 
            serializerfin = InvestigacionFinancieraSerializer(data=data)# Crear el serializer con los datos enviados en la petición
            if serializerfin.is_valid():  # Validar los datos antes de guardarlos
                documentos = []
                print("antes de For",data_documentos)
                for field in documentos:
                    print("campo", field)
                    if field in request.FILES:
                        data_documentos[field] = request.FILES[field]
                    else:
                        data_documentos[field] = None
                
                print("aqui estan tus documentos :D", data_documentos)
                prospecto = serializerfin.save(user = request.user)
                data_documentos["prospecto"] = prospecto.id  
                
                print("serializer", data_documentos)
                documentos_serializer = DocumentosFinancieraSerializer(data=data_documentos)
                documentos_serializer.is_valid()     
                documentos_serializer.save(user = request.user)
                print("Guardado")
                # Guardar el objeto con el usuario autenticado
                return Response({'prospecto': serializerfin.data}, status=status.HTTP_201_CREATED)
                
            
            else:
                # Si la validación falla, devolver los errores
                return Response({'Error al guardar datos': serializerfin.errors}, status=status.HTTP_400_BAD_REQUEST)

        except Exception as e:
            # Captura general de errores
            print(f"error: {e}")
            exc_type, exc_obj, exc_tb = sys.exc_info()
            logger.error(f"{datetime.now()} Ocurrió un error en el archivo {exc_tb.tb_frame.f_code.co_filename}, "
                         f"en el método {exc_tb.tb_frame.f_code.co_name}, en la línea {exc_tb.tb_lineno}: {e}")
            return Response({'error': str(e)}, status=status.HTTP_400_BAD_REQUEST)
    
    
    def investigacion_financiera(self, request, *args, **kwargs):
        try:
            print("entrando en Aprobar prospecto")
            #Consulta para obtener el inquilino y establecemos fecha de hoy
            today = date.today().strftime('%d/%m/%Y')
            req_dat = request.data
            info = Investigacion_Financiera.objects.filter(id = req_dat["id"]).first()
      
            redes_negativo = req_dat.get("redes_negativo")
            print("request.data",req_dat)
            print("el id que llega", req_dat["id"])
            print("")
            print("soy la info del",info.nombre_completo)       
            print(info.__dict__)
            print("")                                     
            print("")
            print("redes negativo", redes_negativo)            
            print("")
            
            requisitos = ['referencia1', 'referencia2', 'referencia3'] # una lista para verificar las referencias 1,2 y 3
            presentes = [req for req in requisitos if req in request.data and request.data[req]]
            print("Referencias presentes: ",presentes)
            if len(presentes) == 3:
                referencias = "En consideración a lo referido por las referencias podemos constatar que la informacion brindada por el prospecto al inicio del tramite es verídica, lo cual nos permite estimar que cuenta con buenos comentarios hacia su persona."
            elif len(presentes) > 0:
                referencias = "En cuanto a la recolección de información de las referencias, no podemos asegurar la veracidad del perfil social del prospecto, ya que no se logró establecer comunicación con las referencias proporcionadas. Por lo tanto, no podemos confirmar completamente la veracidad de la información en la solicitud de arrendamiento. "
            else:
                referencias = "No se pudo recolectar información de las referencias proporcionadas, ya que no se logró establecer comunicación con ninguna de ellas. Por lo tanto, no podemos asegurar la veracidad de la información contenida en la solicitud de arrendamiento ni confirmar el perfil social del prospecto. "
            
            #comentarios de redes para walden
            if redes_negativo:
                redes_negativo = dict(redes_negativo)
                #inicializamos la lista 
                redes_comentarios = []
                #establecemos las frases
                conductas = {
                'conducta_violenta': "Conducta violenta o agresiva: Publicaciones que muestran armas de fuego u otros objetos peligrosos.",
                'conducta_discriminatoria': "Conducta discriminatoria o racista: Comentarios, imágenes o memes que promueven el racismo, sexismo, homofobia, transfobia u otro tipo de discriminación.",
                'contenido_ofensivo_odio': "Contenido ofensivo o de odio: Publicaciones que contienen discursos de odio contra diversos grupos étnicos, religiosos, de orientación sexual, género, etc",
                'bullying_acoso': "Bullying o acoso: Participación en o incitación al acoso, ya sea ciberacoso o en la vida real.",
                'contenido_inapropiado': "Contenido inapropiado o explícito: Publicaciones de contenido sexual explícito o inapropiado.",
                'desinformacion_teoria': "Desinformación y teorías conspirativas: Difusión de información falsa o engañosa, así como la promoción de teorías conspirativas sin fundamento que puedan poner en peligro la tranquilidad y orden dentro de la comunidad.",
                'lenguaje_vulgar': "Lenguaje vulgar o inapropiado: Uso excesivo de lenguaje vulgar o soez en sus publicaciones.",
                'contenido_poco_profesional': "Conducta poco profesional: Publicaciones que muestran comportamientos inapropiados en contextos profesionales.",
                'falta_integridad': "Falta de integridad: Inconsistencias en la información compartida en diferentes plataformas, o indicios de comportamientos engañosos o fraudulentos.",
                'divulgacion_info': "Divulgación de información confidencial: Publicaciones que revelan información privada o confidencial de empresas, clientes o individuos.",
                'exceso_negatividad': "Exceso de negatividad: Publicaciones predominantemente negativas o quejumbrosas.",
                'falta_respeto_priv': "Falta de respeto hacia la privacidad: Compartir información privada de otras personas sin su consentimiento.",
                'ausencia_diversidad': "Ausencia de diversidad y tolerancia: Falta de representación de diversas perspectivas y falta de respeto por la diversidad en sus publicaciones."
                }
                # Bucle para generar las frases basadas en los valores de redes_negativo
                for clave, valor in redes_negativo.items(): #hacemos un for basado en la clave valor del dicciones redes_negativo en el .items al ser un diccionario
                    if valor == "Si" and clave in conductas:
                        frase = conductas[clave]
                        #lo agregamos a la lista redes_comentarios
                        redes_comentarios.append(frase)
                        print("clave:", clave)
                        print("frase:", frase)
                        print("lista finalizada:", redes_comentarios)
                    elif valor == "Si" and clave not in conductas:
                        print(f"No hay una frase definida para la clave: {clave}")
            else:
                redes_comentarios = "no tengo datos"
                print("redes coments",redes_comentarios)
        
            #opciones para el score interno de nosotros
            opciones = {
                'Excelente': "https://arrendifystorage.s3.us-east-2.amazonaws.com/Recursos/medidores/medidor_excelente.png",
                'Bueno': "https://arrendifystorage.s3.us-east-2.amazonaws.com/Recursos/medidores/medidor_bueno.png",
                'Regular': "https://arrendifystorage.s3.us-east-2.amazonaws.com/Recursos/medidores/medidor_regular.png",
                'Malo': "https://arrendifystorage.s3.us-east-2.amazonaws.com/Recursos/medidores/medidor_malo.png"
            }
            
            tipo_score_ingreso = req_dat["tipo_score_ingreso"]
            tipo_score_pp = req_dat["tipo_score_pp"]
            tipo_score_credito = req_dat["tipo_score_credito"]
            
            if tipo_score_ingreso and tipo_score_pp and tipo_score_credito in opciones:
                tsi = opciones[tipo_score_ingreso]
                tspp = opciones[tipo_score_pp]
                tsc = opciones[tipo_score_credito]
                print(f"Tu Tipo de score ingresos es: {tipo_score_ingreso}, URL: {tsi}")
                print(f"Tu Tipo de score de pagos puntuales es: {tipo_score_pp}, URL: {tspp}")
                print(f"Tu Tipo de score de credito es: {tipo_score_credito}, URL: {tsc}")
            
            #evaluar el historial crediticio
            # if tipo_score_pp == "Excelente" and tipo_score_ingreso == "Excelente":
            #     print("aprobado")
            # elif tipo_score_pp != "Malo" and tipo_score_ingreso != "Excelente":
            #     print("a considerar")
            # else:
            #     print("rechazado")
            
            
            
            #evaluar el historial crediticio antes para no hacerlo 2 veces
            # if tipo_score_pp == "Excelente" and tipo_score_ingreso == "Excelente":
            #         print("aprobado")
            #         status = "Aprobado"
            #         conclusion = f"Nos complace informar que el prospecto {info.inquilino.nombre} {info.inquilino.apellido} {info.inquilino.apellido1} ha sido aprobado tras una rigurosa investigación llevada a cabo por el equipo legal de ARRENDIFY S.A.P.I. de C.V. Los resultados obtenidos en todos los parámetros evaluados se encuentran dentro del rango de tolerancia establecido por los criterios de evaluación de la empresa. Esto confirma que el candidato cumple con los requisitos y estándares exigidos, validando así su idoneidad para el arrendamiento en cuestión."
            
            # elif tipo_score_pp != "Malo" and tipo_score_ingreso != "Excelente":
            #     print("a considerar")
            #     status = "A considerar"
            #     conclusion = ""
                
            # else:
            #     print("rechazado") 
               
               
            #Dar conclusion dinamica
            antecedentes = request.data.get('antecedentes') # Obtenemos todos los antecedentes del prospecto
            print("ANTECEDENTES",antecedentes)
            if antecedentes:
                # del antecedentes["civil_mercantil_demandado"] 
                print("tienes antecedences, vamos a ver si es civil o familiar",antecedentes)
                if antecedentes.get("civil_mercantil_demandado") and len(antecedentes) == 1: #tiene antecedentes de civil o de familiar? los excentamos si no delincuente
                    print("Tiene antecedentes civiles o familiares")
                    print("Checamos el historial")
                    #evaluar el historial crediticio  
                    
                    if tipo_score_pp == "Malo" or tipo_score_ingreso == "Malo":
                        print("rechazado")
                        conclusion = "Lamentamos informar que el candidato ha sido rechazado tras el análisis de riesgo realizado por ARRENDIFY S.A.P.I. de C.V. Los resultados de la investigación determinan que es inseguro arrendar el inmueble al prospecto debido a los aspectos que se han detallado en lo expuesto anteriormente respecto a:"    
                        motivo = "1.- Buro: Se cuenta con un buro en con atrasos y/o adeudos, estos datos se detallan en el apartado correspondiente."
                    
                    elif tipo_score_pp == "Excelente" and tipo_score_ingreso == "Excelente" or tipo_score_pp == "Excelente" and tipo_score_ingreso == "Bueno" or tipo_score_pp == "Bueno" and tipo_score_ingreso == "Excelente":
                        print("aprobado")
                        conclusion = f"Nos complace informar que el prospecto {info.nombre_completo} ha sido aprobado tras una rigurosa investigación llevada a cabo por el equipo legal de ARRENDIFY S.A.P.I. de C.V. Los resultados obtenidos en todos los parámetros evaluados se encuentran dentro del rango de tolerancia establecido por los criterios de evaluación de la empresa. Esto confirma que el candidato cumple con los requisitos y estándares exigidos, validando así su idoneidad para el arrendamiento en cuestión."
                        motivo = "No hay motivo de rechazo"
                    
                    elif tipo_score_pp != "Malo" and tipo_score_ingreso != "Malo":
                        print("a considerar")
                        conclusion = "Nos complace informar que el candidato ha sido aprobado tras una rigurosa investigación llevada a cabo por ARRENDIFY S.A.P.I. de C.V. Los resultados obtenidos en todos los parámetros evaluados se encuentran dentro del rango de tolerancia establecido por los criterios de evaluación de la empresa, confirmando así que el candidato cumple con los requisitos exigidos. \n \n No obstante, es importante considerar que la investigación ha revelado ciertos puntos que deben tomarse en cuenta, los cuales se detallado en lo expuesto anteriormente respecto a:"
                        motivo = "1.- Antecedentes: Se cuenta con demanda en materia civil o familiar.\n2.- Buro: Historial crediticio con algunas áreas que podrían mejorarse."
                    
                elif antecedentes and tipo_score_pp == "Malo" or antecedentes and tipo_score_ingreso == "Malo":
                        print("rechazado")
                        conclusion = "Lamentamos informar que el candidato ha sido rechazado tras el análisis de riesgo realizado por ARRENDIFY S.A.P.I. de C.V. Los resultados de la investigación determinan que es inseguro arrendar el inmueble al prospecto debido a los aspectos que se han detallado en lo expuesto anteriormente respecto a:"    
                        motivo = "1.- Buro: Se cuenta con un buro en con atrasos y/o adeudos, estos datos se detallan en el apartado correspondiente.\n2.- Antecedentes: Se cuenta con antecedentes legales, que se detallan en el apartado correspondiente."    
                        
                else:
                    print("eres un delincuente")
                    conclusion = "Lamentamos informar que el candidato ha sido rechazado tras el análisis de riesgo realizado por ARRENDIFY S.A.P.I. de C.V. Los resultados de la investigación determinan que es inseguro arrendar el inmueble al prospecto debido a los aspectos que se han detallado en lo expuesto anteriormente respecto a:"    
                    motivo = "1.- Antecedentes: Se cuenta con antecedentes legales, que se detallan en el apartado correspondiente."
            else: #No tiene Antecedentes
                
                #evaluar el historial crediticio  
                if tipo_score_pp == "Malo" or tipo_score_ingreso == "Malo":
                    print("rechazado")
                    conclusion = "Lamentamos informar que el candidato ha sido rechazado tras el análisis de riesgo realizado por ARRENDIFY S.A.P.I. de C.V. Los resultados de la investigación determinan que es inseguro arrendar el inmueble al prospecto debido a los aspectos que se han detallado en lo expuesto anteriormente respecto a:"    
                    motivo = "1.- Buro: Se cuenta con un buro en con atrasos y/o adeudos, estos datos se detallan en el apartado correspondiente."
                
                elif tipo_score_pp == "Excelente" and tipo_score_ingreso == "Excelente" or tipo_score_pp == "Excelente" and tipo_score_ingreso == "Bueno" or tipo_score_pp == "Bueno" and tipo_score_ingreso == "Excelente":
                    print("aprobado")
                    conclusion = f"Nos complace informar que el prospecto {info.nombre_completo} ha sido aprobado tras una rigurosa investigación llevada a cabo por el equipo legal de ARRENDIFY S.A.P.I. de C.V. Los resultados obtenidos en todos los parámetros evaluados se encuentran dentro del rango de tolerancia establecido por los criterios de evaluación de la empresa. Esto confirma que el candidato cumple con los requisitos y estándares exigidos, validando así su idoneidad para el arrendamiento en cuestión."
                    motivo = "hola"   
                
                elif tipo_score_pp != "Malo" and tipo_score_ingreso != "Malo":
                    print("a considerar")
                    conclusion = "Nos complace informar que el candidato ha sido aprobado tras una rigurosa investigación llevada a cabo por ARRENDIFY S.A.P.I. de C.V. Los resultados obtenidos en todos los parámetros evaluados se encuentran dentro del rango de tolerancia establecido por los criterios de evaluación de la empresa, confirmando así que el candidato cumple con los requisitos exigidos. \n \n No obstante, es importante considerar que la investigación ha revelado ciertos puntos que deben tomarse en cuenta, los cuales se detallado en lo expuesto anteriormente respecto a:"
                    motivo = "1.- Buro: Historial crediticio con algunas áreas que podrían mejorarse."
                
                 
                    
            context = {'info': info, "fecha_consulta":today, 'datos':req_dat, 'tsi':tsi, 'tspp':tspp, 'tsc':tsc, 
                       "redes_comentarios":redes_comentarios, 'referencias':referencias, 'antecedentes':antecedentes,'conclusion':conclusion, 'motivo':motivo}
            
            template = 'home/report_financiero.html'
            html_string = render_to_string(template, context)

            # Genera el PDF utilizando weasyprint
            print("Generando el pdf")
            pdf_file = HTML(string=html_string).write_pdf()
            #aqui hacia abajo es para enviar por email
            # archivo = ContentFile(pdf_file, name='aprobado.pdf') # lo guarda como content raw para enviar el correo
        
            # print("antes de enviar_archivo",context)
            # self.enviar_archivo(archivo, context["info"], context["status"])
            
            # # Aprobar o desaprobar
            if info.status == "Pendiente":  
                 print("status de inquilino",info.status)
                 info.status = "Revisado"
                 info.save()
                 print("status cambiado",info.status)
                 info.save()
            
            # print("PDF ENVIADO")
            
            # return Response({'mensaje': "Todo salio bien, pdf enviado"}, status = "200")
           
            # de aqui hacia abajo Devuelve esl PDF como respuesta
            response = HttpResponse(content_type='application/pdf')
            response['Content-Disposition'] = 'attachment; filename="Pagare.pdf"'
            response.write(pdf_file)
            print("Finalizamos el proceso de aprobado") 
            return HttpResponse(response, content_type='application/pdf')
        
        except Exception as e:
            print(f"el error es: {e}")
            exc_type, exc_obj, exc_tb = sys.exc_info()
            logger.error(f"{datetime.now()} Ocurrió un error en el archivo {exc_tb.tb_frame.f_code.co_filename}, en el método {exc_tb.tb_frame.f_code.co_name}, en la línea {exc_tb.tb_lineno}:  {e}")
            return Response({'error': str(e)}, status = "404") 


class InvestigacionJudicialViewSet(viewsets.ViewSet):
      # Autenticación y permisos
    authentication_classes = [TokenAuthentication, SessionAuthentication]
    permission_classes = [IsAuthenticated]
    serializer_class = InvestigacionJudicialSerializer
    queryset = Investigacion_Judicial.objects.all()
    
    
    def list(self, request, *args, **kwargs):
        user_session = request.user
        try:    
            if request.method == 'GET':
                if user_session.is_staff:
                    snippets = Investigacion_Judicial.objects.all().order_by('-id')
                    
                    # Crear una copia de los datos serializados
                    serializer = InvestigacionJudicialSerializer(snippets, many=True)
                    serialized_data = serializer.data

                    # Agregar el campo 'is_staff'
                    for item in serialized_data:
                        item['is_staff'] = True

                    # Devolver la respuesta
                    return Response(serialized_data)
                
                    # Listar muchos a muchos
                    # Obtener todos las investigaciones del usuario actual
                investigacion_propia = Investigacion_Judicial.objects.all().filter(user_id = user_session)
                print(investigacion_propia)
   
                serializer = InvestigacionJudicialSerializer(snippets, many=True)
            
                return Response(serializer.data)
            
        except Exception as e:
            print(f"el error es: {e}")
            exc_type, exc_obj, exc_tb = sys.exc_info()
            logger.error(f"{datetime.now()} Ocurrió un error en el archivo {exc_tb.tb_frame.f_code.co_filename}, en el método {exc_tb.tb_frame.f_code.co_name}, en la línea {exc_tb.tb_lineno}:  {e}")
            return Response({'error': str(e)}, status=status.HTTP_400_BAD_REQUEST)
    
    def create(self, request, *args, **kwargs):
        try:
            data_documentos ={}
            print("entro a post")
            data = request.data # Crea una copia de los datos
            serializerjud = InvestigacionJudicialSerializer(data=data) # Crear el serializer con los datos enviados en la petición
            
            if serializerjud.is_valid():  # Validar los datos antes de guardarlos
                documentos = ['identificacion_doc','comprobante_domicilio','comprobante_ingresos','situacionfiscal','carta_laboral']
                print("antes de For:",data_documentos)
                for field in documentos:
                    print("campo", field)
                    if field in request.FILES:
                        data_documentos[field] = request.FILES[field]
                    else:
                        data_documentos[field] = None

                print("aqui estan los documentos :D",data_documentos)
                prospecto = serializerjud.save(user = request.user)
                data_documentos["prospecto"] = prospecto.id 
                
                documentos_serializer = DocumentosJudicialSerializer(data=data_documentos)
                documentos_serializer.is_valid()
                documentos_serializer.save(user = request.user)
                print("Guardado")         
                return Response({'prospecto': serializerjud.data}, status=status.HTTP_201_CREATED) # Guardar el objeto
            
            else:
                # Si la validación falla, devolver los errores
                return Response(serializerjud.errors, status=status.HTTP_400_BAD_REQUEST)

        except Exception as e:
            # Captura general de errores
            exc_type, exc_obj, exc_tb = sys.exc_info()
            logger.error(f"{datetime.now()} Ocurrió un error en el archivo {exc_tb.tb_frame.f_code.co_filename}, "
                         f"en el método {exc_tb.tb_frame.f_code.co_name}, en la línea {exc_tb.tb_lineno}: {e}")
            return Response({'error': str(e)}, status=status.HTTP_400_BAD_REQUEST)
        

    def investigacion_judicial (self, request, *args, **kwargs):
        print("Investigacion Judicial")
        try:
                print("entrando en Aprobar prospecto")
                #Consulata para obtener el inquilino y establecemos fecha de hoy
                today = date.today().strftime('%d/%m/%Y')
                req_dat = request.data
                info = Investigacion_Judicial.objects.filter(id = req_dat["id"]).first()
                print("soy INFO",info.__dict__)         
                
                print("")
                print("soy la info del",info.nombre_completo)       

                requisitos = ['referencia1', 'referencia2', 'referencia3'] # una lista para verificar las referencias 1,2 y 3
                presentes = [req for req in requisitos if req in request.data and request.data[req]]
                print("Referencias presentes: ",presentes)
                if len(presentes) == 3:
                    referencias = "En consideración a lo referido por las referencias podemos constatar que la informacion brindada por el prospecto al inicio del tramite es verídica, lo cual nos permite estimar que cuenta con buenos comentarios hacia su persona."
                elif len(presentes) > 0:
                    referencias = "En cuanto a la recolección de información por parte de las referencias se nos imposibilita aseverar la cabalidad de la persona a investigar referente a su ámbito social, toda vez que no se logró entablar comunicación con alguna(s) referencias proporcionadas, por lo tanto, no podemos corroborar por completo la veracidad de la información proporcionada en la solicitud de arrendamiento. "
                else:
                    referencias = "En cuanto a la recolección de información por parte de las referencias se nos imposibilita aseverar la cabalidad de la persona a investigar referente a su ámbito social, toda vez que no se logró entablar comunicación con ninguna de las referencias proporcionadas, por lo tanto, no podemos corroborar la veracidad de la información proporcionada en la solicitud de arrendamiento. "
                
                opciones = {
                    'Excelente': "https://arrendifystorage.s3.us-east-2.amazonaws.com/Recursos/medidores/medidor_excelente.png",
                    'Bueno': "https://arrendifystorage.s3.us-east-2.amazonaws.com/Recursos/medidores/medidor_bueno.png",
                    'Regular': "https://arrendifystorage.s3.us-east-2.amazonaws.com/Recursos/medidores/medidor_regular.png",
                    'Malo': "https://arrendifystorage.s3.us-east-2.amazonaws.com/Recursos/medidores/medidor_malo.png"
                }
                
                tipo_score_ingreso = req_dat["tipo_score_ingreso"]
                tipo_score_pp = req_dat["tipo_score_pp"]
                tipo_score_credito = req_dat["tipo_score_credito"]
                
                if tipo_score_ingreso and tipo_score_pp and tipo_score_credito in opciones:
                    tsi = opciones[tipo_score_ingreso]
                    tspp = opciones[tipo_score_pp]
                    tsc = opciones[tipo_score_credito]
                    print(f"Tu Tipo de score ingresos es: {tipo_score_ingreso}, URL: {tsi}")
                    print(f"Tu Tipo de score de pagos puntuales es: {tipo_score_pp}, URL: {tspp}")
                    print(f"Tu Tipo de score de credito es: {tipo_score_credito}, URL: {tsc}")

                
                #Dar conclusion dinamica
                antecedentes = request.data.get('antecedentes') # Obtenemos todos los antecedentes del prospecto
                print("ANTECEDENTES",antecedentes)
                if antecedentes:
                    # del antecedentes["civil_mercantil_demandado"] 
                    print("tienes antecedences, vamos a ver si es civil o familiar",antecedentes)
                    if antecedentes.get("civil_mercantil_demandado") and len(antecedentes) == 1: #tiene antecedentes de civil o de familiar? los excentamos si no delincuente
                        print("Tiene antecedentes civiles o familiares")
                        print("Checamos el historial")
                        #evaluar el historial crediticio  
                        
                        if tipo_score_pp == "Malo" or tipo_score_ingreso == "Malo":
                            print("rechazado")
                            conclusion = "Lamentamos informar que el candidato ha sido rechazado tras el análisis de riesgo realizado por ARRENDIFY S.A.P.I. de C.V. Los resultados de la investigación determinan que es inseguro arrendar el inmueble al prospecto debido a los aspectos que se han detallado en lo expuesto anteriormente respecto a:"    
                            motivo = "1.- Buro: Se cuenta con un buro en con atrasos y/o adeudos, estos datos se detallan en el apartado correspondiente."
                        
                        elif tipo_score_pp == "Excelente" and tipo_score_ingreso == "Excelente" or tipo_score_pp == "Excelente" and tipo_score_ingreso == "Bueno" or tipo_score_pp == "Bueno" and tipo_score_ingreso == "Excelente":
                            print("aprobado")
                            conclusion = f"Nos complace informar que el prospecto {info.nombre_completo} ha sido aprobado tras una rigurosa investigación llevada a cabo por el equipo legal de ARRENDIFY S.A.P.I. de C.V. Los resultados obtenidos en todos los parámetros evaluados se encuentran dentro del rango de tolerancia establecido por los criterios de evaluación de la empresa. Esto confirma que el candidato cumple con los requisitos y estándares exigidos, validando así su idoneidad para el arrendamiento en cuestión."
                            motivo = "No hay motivo de rechazo"
                        
                        elif tipo_score_pp != "Malo" and tipo_score_ingreso != "Malo":
                            print("a considerar")
                            conclusion = "Nos complace informar que el candidato ha sido aprobado tras una rigurosa investigación llevada a cabo por ARRENDIFY S.A.P.I. de C.V. Los resultados obtenidos en todos los parámetros evaluados se encuentran dentro del rango de tolerancia establecido por los criterios de evaluación de la empresa, confirmando así que el candidato cumple con los requisitos exigidos. \n \n No obstante, es importante considerar que la investigación ha revelado ciertos puntos que deben tomarse en cuenta, los cuales se detallado en lo expuesto anteriormente respecto a:"
                            motivo = "1.- Antecedentes: Se cuenta con demanda en materia civil o familiar.\n2.- Buro: Historial crediticio con algunas áreas que podrían mejorarse."
                        
                    elif antecedentes and tipo_score_pp == "Malo" or antecedentes and tipo_score_ingreso == "Malo":
                            print("rechazado")
                            conclusion = "Lamentamos informar que el candidato ha sido rechazado tras el análisis de riesgo realizado por ARRENDIFY S.A.P.I. de C.V. Los resultados de la investigación determinan que es inseguro arrendar el inmueble al prospecto debido a los aspectos que se han detallado en lo expuesto anteriormente respecto a:"    
                            motivo = "1.- Buro: Se cuenta con un buro en con atrasos y/o adeudos, estos datos se detallan en el apartado correspondiente.\n2.- Antecedentes: Se cuenta con antecedentes legales, que se detallan en el apartado correspondiente."    
                            
                    else:
                        print("eres un delincuente")
                        conclusion = "Lamentamos informar que el candidato ha sido rechazado tras el análisis de riesgo realizado por ARRENDIFY S.A.P.I. de C.V. Los resultados de la investigación determinan que es inseguro arrendar el inmueble al prospecto debido a los aspectos que se han detallado en lo expuesto anteriormente respecto a:"    
                        motivo = "1.- Antecedentes: Se cuenta con antecedentes legales, que se detallan en el apartado correspondiente."
                else: #No tiene Antecedentes
                    
                    #evaluar el historial crediticio  
                    if tipo_score_pp == "Malo" or tipo_score_ingreso == "Malo":
                        print("rechazado")
                        conclusion = "Lamentamos informar que el candidato ha sido rechazado tras el análisis de riesgo realizado por ARRENDIFY S.A.P.I. de C.V. Los resultados de la investigación determinan que es inseguro arrendar el inmueble al prospecto debido a los aspectos que se han detallado en lo expuesto anteriormente respecto a:"    
                        motivo = "1.- Buro: Se cuenta con un buro en con atrasos y/o adeudos, estos datos se detallan en el apartado correspondiente."
                    
                    elif tipo_score_pp == "Excelente" and tipo_score_ingreso == "Excelente" or tipo_score_pp == "Excelente" and tipo_score_ingreso == "Bueno" or tipo_score_pp == "Bueno" and tipo_score_ingreso == "Excelente":
                        print("aprobado")
                        conclusion = f"Nos complace informar que el prospecto {info.nombre_completo} ha sido aprobado tras una rigurosa investigación llevada a cabo por el equipo legal de ARRENDIFY S.A.P.I. de C.V. Los resultados obtenidos en todos los parámetros evaluados se encuentran dentro del rango de tolerancia establecido por los criterios de evaluación de la empresa. Esto confirma que el candidato cumple con los requisitos y estándares exigidos, validando así su idoneidad para el arrendamiento en cuestión."
                        motivo = "hola"   
                    
                    elif tipo_score_pp != "Malo" and tipo_score_ingreso != "Malo":
                        print("a considerar")
                        conclusion = "Nos complace informar que el candidato ha sido aprobado tras una rigurosa investigación llevada a cabo por ARRENDIFY S.A.P.I. de C.V. Los resultados obtenidos en todos los parámetros evaluados se encuentran dentro del rango de tolerancia establecido por los criterios de evaluación de la empresa, confirmando así que el candidato cumple con los requisitos exigidos. \n \n No obstante, es importante considerar que la investigación ha revelado ciertos puntos que deben tomarse en cuenta, los cuales se detallado en lo expuesto anteriormente respecto a:"
                        motivo = "1.- Buro: Historial crediticio con algunas áreas que podrían mejorarse."
                        
                context = {'info': info, "fecha_consulta":today, 'datos':req_dat, 'tsi':tsi, 'tspp':tspp, 'tsc':tsc, 
                        'referencias':referencias, 'antecedentes':antecedentes, 'conclusion':conclusion, 'motivo':motivo}
            
                
                template = 'home/report_judicial.html'
                html_string = render_to_string(template, context)

                # Genera el PDF utilizando weasyprint
                print("Generando el pdf")
                pdf_file = HTML(string=html_string).write_pdf()
                #aqui hacia abajo es para enviar por email
                # archivo = ContentFile(pdf_file, name='aprobado.pdf') # lo guarda como content raw para enviar el correo
            
                # print("antes de enviar_archivo",context)
                # self.enviar_archivo(archivo, context["info"], context["status"])
                
            # Aprobar o desaprobar
                if info.status == "Pendiente":  
                    print("status de inquilino",info.status)
                    info.status = "Revisado"
                    info.save()
                    print("status cambiado",info.status)
                    info.save()
                
                print("PDF ENVIADO")
                
                # return Response({'mensaje': "Todo salio bien, pdf enviado"}, status = "200")
            
                # de aqui hacia abajo Devuelve esl PDF como respuesta
                response = HttpResponse(content_type='application/pdf')
                response.write(pdf_file)
                print("Finalizamos el proceso de aprobado") 
                return HttpResponse(response, content_type='application/pdf')
        
        except Exception as e:
                print(f"el error es: {e}")
                exc_type, exc_obj, exc_tb = sys.exc_info()
                logger.error(f"{datetime.now()} Ocurrió un error en el archivo {exc_tb.tb_frame.f_code.co_filename}, en el método {exc_tb.tb_frame.f_code.co_name}, en la línea {exc_tb.tb_lineno}:  {e}")
                return Response({'error': str(e)}, status = "404") 