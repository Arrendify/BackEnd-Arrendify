# -*- encoding: utf-8 -*-
"""
Comando de Django para verificar contratos próximos a vencer
y generar recordatorios automáticos por email y notificaciones internas
"""

from django.core.management.base import BaseCommand
from django.utils import timezone
from django.core.mail import send_mail
from django.conf import settings
from django.contrib.auth.models import User
from django.db.models import Q
from datetime import date, timedelta
from dateutil.relativedelta import relativedelta

from apps.home.models import (
    Contratos, FraternaContratos, SemilleroContratos, 
    GarzaSadaContratos, Notificacion
)
from ....accounts.models import CustomUser
User = CustomUser

class Command(BaseCommand):
    help = 'Verifica contratos próximos a vencer y envía recordatorios automáticos'

    def add_arguments(self, parser):
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Ejecuta el comando sin enviar emails ni crear notificaciones (solo muestra lo que haría)',
        )
        parser.add_argument(
            '--force',
            action='store_true',
            help='Fuerza el envío de recordatorios aunque ya existan',
        )

    def handle(self, *args, **options):
        self.dry_run = options['dry_run']
        self.force = options['force']
        
        self.stdout.write(
            self.style.SUCCESS(f'Iniciando verificación de contratos - {timezone.now()}')
        )
        
        if self.dry_run:
            self.stdout.write(
                self.style.WARNING('MODO DRY-RUN: No se enviarán emails ni crearán notificaciones')
            )

        # Verificar cada tipo de contrato
        self.verificar_contratos_generales()
        self.verificar_contratos_fraterna()
        self.verificar_contratos_semillero()
        self.verificar_contratos_garzasada()
        
        self.stdout.write(
            self.style.SUCCESS('Verificación completada exitosamente')
        )

    def verificar_contratos_generales(self):
        """Verifica contratos generales próximos a vencer"""
        self.stdout.write('Verificando contratos generales...')
        
        # Obtener contratos con datos_contratos que contengan fecha_vigencia
        contratos = Contratos.objects.filter(
            datos_contratos__isnull=False
        ).exclude(
            datos_contratos={}
        )
        
        self.stdout.write(f'Encontrados {contratos.count()} contratos generales con datos')
        
        for contrato in contratos:
            try:
                datos = contrato.datos_contratos
                self.stdout.write(f'Procesando contrato {contrato.id} - Usuario: {contrato.user}')
                if 'fecha_termino' in datos and datos['fecha_termino']:
                    self.stdout.write(f'Fecha vigencia encontrada: {datos["fecha_termino"]}')
                    fecha_vigencia = self.parse_fecha(datos['fecha_termino'])
                    if fecha_vigencia:
                        self.stdout.write(f'Fecha parseada: {fecha_vigencia}')
                        self.procesar_recordatorios_contrato(
                            contrato, fecha_vigencia, 'general', contrato_general=contrato
                        )
                    else:
                        self.stdout.write(f'No se pudo parsear la fecha: {datos["fecha_vigencia"]}')
                else:
                    self.stdout.write('No tiene fecha_vigencia en datos_contratos')
            except Exception as e:
                self.stdout.write(
                    self.style.ERROR(f'Error procesando contrato general {contrato.id}: {e}')
                )

    def verificar_contratos_fraterna(self):
        """Verifica contratos Fraterna próximos a vencer"""
        self.stdout.write('Verificando contratos Fraterna...')
        
        contratos = FraternaContratos.objects.filter(
            fecha_vigencia__isnull=False
        )
        
        self.stdout.write(f'Encontrados {contratos.count()} contratos Fraterna con fecha_vigencia')
        
        for contrato in contratos:
            try:
                self.stdout.write(f'Procesando contrato Fraterna {contrato.id} - Usuario: {contrato.user}')
                self.stdout.write(f'Fecha vigencia encontrada: {contrato.fecha_vigencia}')
                self.procesar_recordatorios_contrato(
                    contrato, contrato.fecha_vigencia, 'fraterna', contrato_fraterna=contrato
                )
            except Exception as e:
                self.stdout.write(
                    self.style.ERROR(f'Error procesando contrato Fraterna {contrato.id}: {e}')
                )
    
    def verificar_contratos_semillero(self):
        """Verifica contratos Semillero próximos a vencer"""
        self.stdout.write('Verificando contratos Semillero...')
        
        contratos = SemilleroContratos.objects.filter(
            fecha_celebracion__isnull=False,
            duracion__isnull=False
        )
        
        self.stdout.write(f'Encontrados {contratos.count()} contratos Semillero con fecha_celebracion y duracion')
        
        for contrato in contratos:
            try:
                self.stdout.write(f'Procesando contrato Semillero {contrato.id} - Usuario: {contrato.user}')
                self.stdout.write(f'Fecha celebración: {contrato.fecha_celebracion}, Duración: {contrato.duracion}')
                fecha_vigencia = self.calcular_fecha_vigencia(
                    contrato.fecha_celebracion, contrato.duracion
                )
                if fecha_vigencia:
                    self.stdout.write(f'Fecha vigencia calculada: {fecha_vigencia}')
                    self.procesar_recordatorios_contrato(
                        contrato, fecha_vigencia, 'semillero', contrato_semillero=contrato
                    )
                else:
                    self.stdout.write('No se pudo calcular fecha_vigencia')
            except Exception as e:
                self.stdout.write(
                    self.style.ERROR(f'Error procesando contrato Semillero {contrato.id}: {e}')
                )
    
    def verificar_contratos_garzasada(self):
        """Verifica contratos Garza Sada próximos a vencer"""
        self.stdout.write('Verificando contratos Garza Sada...')
        
        contratos = GarzaSadaContratos.objects.filter(
            fecha_celebracion__isnull=False,
            duracion__isnull=False
        )
        
        self.stdout.write(f'Encontrados {contratos.count()} contratos Garza Sada con fecha_celebracion y duracion')
        
        for contrato in contratos:
            try:
                self.stdout.write(f'Procesando contrato Garza Sada {contrato.id} - Usuario: {contrato.user}')
                self.stdout.write(f'Fecha celebración: {contrato.fecha_celebracion}, Duración: {contrato.duracion}')
                fecha_vigencia = self.calcular_fecha_vigencia(
                    contrato.fecha_celebracion, contrato.duracion
                )
                if fecha_vigencia:
                    self.stdout.write(f'Fecha vigencia calculada: {fecha_vigencia}')
                    self.procesar_recordatorios_contrato(
                        contrato, fecha_vigencia, 'garzasada', contrato_garzasada=contrato
                    )
                else:
                    self.stdout.write('No se pudo calcular fecha_vigencia')
            except Exception as e:
                self.stdout.write(
                    self.style.ERROR(f'Error procesando contrato Garza Sada {contrato.id}: {e}')
                )
    
    def procesar_recordatorios_contrato(self, contrato, fecha_vigencia, tipo_contrato, **kwargs):
        """Procesa los recordatorios para un contrato específico"""
        self.stdout.write(f'Procesando recordatorios para contrato {tipo_contrato} - Fecha vigencia: {fecha_vigencia}')
        
        hoy = date.today()
        self.stdout.write(f'Fecha actual: {hoy}')
        
        # Calcular fechas de recordatorio
        fecha_3_meses = fecha_vigencia - relativedelta(months=3)
        fecha_2_meses = fecha_vigencia - relativedelta(months=2)
        fecha_1_mes = fecha_vigencia - relativedelta(months=1)
        
        self.stdout.write(f'Fechas recordatorio: 3m={fecha_3_meses}, 2m={fecha_2_meses}, 1m={fecha_1_mes}')
        
        recordatorios = [
            ('recordatorio_3_meses', fecha_3_meses, '3 meses'),
            ('recordatorio_2_meses', fecha_2_meses, '2 meses'),
            ('recordatorio_1_mes', fecha_1_mes, '1 mes'),
        ]
        
        for tipo_recordatorio, fecha_recordatorio, descripcion in recordatorios:
            self.stdout.write(f'Verificando recordatorio {descripcion}: fecha={fecha_recordatorio}, hoy={hoy}')
            
            # Si es --force, crear todos los recordatorios
            # Si no es --force, solo crear si es la fecha exacta
            debe_crear = self.force or (fecha_recordatorio == hoy)
            self.stdout.write(f'Debe crear notificación: {debe_crear} (force={self.force}, fecha_exacta={fecha_recordatorio == hoy})')
            
            if debe_crear:
                self.stdout.write(f'Intentando crear notificación {tipo_recordatorio}')
                self.crear_recordatorio(
                    contrato, fecha_vigencia, tipo_recordatorio, 
                    tipo_contrato, descripcion, **kwargs
                )
            else:
                self.stdout.write(f'No es necesario crear notificación para {descripcion}')
    
    def crear_recordatorio(self, contrato, fecha_vigencia, tipo_recordatorio, 
                          tipo_contrato, descripcion, **kwargs):
        """Crea un recordatorio si no existe ya"""
        
        # Verificar si ya existe el recordatorio
        filtros = {
            'tipo_notificacion': tipo_recordatorio,
            'tipo_contrato': tipo_contrato,
            'fecha_vencimiento_contrato': fecha_vigencia,
        }
        filtros.update(kwargs)
        
        if not self.force and Notificacion.objects.filter(**filtros).exists():
            return  # Ya existe el recordatorio
        
        # Obtener información del contrato
        info_contrato = self.obtener_info_contrato(contrato, tipo_contrato)
        usuario = info_contrato.get('usuario')
        
        if not usuario:
            # No cortar el flujo: permitimos crear notificación sin usuario asignado
            self.stdout.write(
                self.style.WARNING(f'No se encontró usuario para contrato {contrato.id}. Creando notificación con user=None')
            )
        
        # Crear título y mensaje
        titulo = f"Recordatorio: Contrato próximo a vencer ({descripcion})"
        mensaje = self.generar_mensaje_recordatorio(info_contrato, fecha_vigencia, descripcion)
        
        if not self.dry_run:
            # Crear notificación
            notificacion = Notificacion.objects.create(
                user=usuario,
                tipo_notificacion=tipo_recordatorio,
                tipo_contrato=tipo_contrato,
                titulo=titulo,
                mensaje=mensaje,
                fecha_vencimiento_contrato=fecha_vigencia,
                fecha_programada=date.today(),
                **kwargs
            )
            
            # Enviar email solo si hay usuario asociado
            if usuario:
                self.enviar_email_recordatorio(usuario, titulo, mensaje, info_contrato)
            
            self.stdout.write(
                self.style.SUCCESS(
                    f'Recordatorio creado para contrato {contrato.id} - {descripcion}'
                )
            )
        else:
            self.stdout.write(
                self.style.WARNING(
                    f'[DRY-RUN] Se crearía recordatorio para contrato {contrato.id} - {descripcion}'
                )
            )

    def obtener_info_contrato(self, contrato, tipo_contrato):
        """Obtiene información relevante del contrato"""
        info = {'usuario': None, 'inmueble': '', 'arrendatario': ''}
        
        try:
            if tipo_contrato == 'fraterna':
                info['inmueble'] = f"Depto {contrato.no_depa or 'N/A'}"
                if contrato.residente:
                    # Para fraterna: usar nombre_arrendatario del residente
                    info['arrendatario'] = str(contrato.residente)
                    nombre_para_buscar = getattr(contrato.residente, 'nombre_arrendatario', None)
                    if nombre_para_buscar:
                        info['usuario'] = self.buscar_usuario_por_nombre(nombre_para_buscar)
                    else:
                        info['usuario'] = contrato.user  # Fallback
                else:
                    info['arrendatario'] = 'N/A'
                    info['usuario'] = contrato.user  # Fallback al usuario del contrato
                
            elif tipo_contrato == 'semillero':
                info['inmueble'] = f"Propiedad {contrato.id}"
                if contrato.arrendatario:
                    # Para semillero: usar nombre_arrendatario del arrendatario
                    nombre_para_buscar = getattr(contrato.arrendatario, 'nombre_arrendatario', None)
                    if nombre_para_buscar:
                        info['arrendatario'] = nombre_para_buscar
                        info['usuario'] = self.buscar_usuario_por_nombre(nombre_para_buscar)
                    else:
                        info['arrendatario'] = str(contrato.arrendatario)
                        info['usuario'] = contrato.user  # Fallback
                else:
                    info['arrendatario'] = 'N/A'
                    info['usuario'] = contrato.user  # Fallback al usuario del contrato
                
            elif tipo_contrato == 'garzasada':
                info['inmueble'] = f"Propiedad {contrato.id}"
                if contrato.arrendatario:
                    # Para garzasada: usar nombre_arrendatario del arrendatario
                    nombre_para_buscar = getattr(contrato.arrendatario, 'nombre_arrendatario', None)
                    if nombre_para_buscar:
                        info['arrendatario'] = nombre_para_buscar
                        info['usuario'] = self.buscar_usuario_por_nombre(nombre_para_buscar)
                    else:
                        info['arrendatario'] = str(contrato.arrendatario)
                        info['usuario'] = contrato.user  # Fallback
                else:
                    info['arrendatario'] = 'N/A'
                    info['usuario'] = contrato.user  # Fallback al usuario del contrato
                
            elif tipo_contrato == 'general':
                info['inmueble'] = str(contrato.inmueble) if contrato.inmueble else 'N/A'
                if contrato.arrendatario:
                    # Para general: usar nombre_completo del arrendatario (si existe)
                    nombre_para_buscar = getattr(contrato.arrendatario, 'nombre_completo', None)
                    if not nombre_para_buscar:
                        # Si no tiene nombre_completo, intentar con otros campos
                        nombre_para_buscar = getattr(contrato.arrendatario, 'nombre_arrendatario', None)
                    
                    if nombre_para_buscar:
                        info['arrendatario'] = nombre_para_buscar
                        info['usuario'] = self.buscar_usuario_por_nombre(nombre_para_buscar)
                    else:
                        info['arrendatario'] = str(contrato.arrendatario)
                        info['usuario'] = contrato.user  # Fallback
                else:
                    info['arrendatario'] = 'N/A'
                    info['usuario'] = contrato.user  # Fallback al usuario del contrato
                
        except Exception as e:
            self.stdout.write(
                self.style.ERROR(f'Error obteniendo info del contrato: {e}')
            )
            # En caso de error, usar el usuario del contrato como fallback
            info['usuario'] = contrato.user
        
        return info

    def buscar_usuario_por_nombre(self, nombre_completo):
        """
        Busca un CustomUser por nombre completo usando lógica similar a fraterna_views.py
        """
        if not nombre_completo:
            return None
            
        try:
            # Limpiar el nombre
            nombre_limpio = nombre_completo.strip()
            
            # Buscar usuario por first_name que coincida con el nombre completo
            usuario = CustomUser.objects.filter(
                Q(first_name__icontains=nombre_limpio)
            ).first()
            
            if usuario:
                self.stdout.write(
                    self.style.SUCCESS(
                        f'Usuario encontrado: {usuario.first_name} (ID: {usuario.id}) para nombre: {nombre_completo}'
                    )
                )
                return usuario
            else:
                self.stdout.write(
                    self.style.WARNING(
                        f'No se encontró CustomUser para el nombre: {nombre_completo}'
                    )
                )
                return None
                
        except Exception as e:
            self.stdout.write(
                self.style.ERROR(f'Error buscando usuario por nombre {nombre_completo}: {e}')
            )
            return None

    def generar_mensaje_recordatorio(self, info_contrato, fecha_vigencia, descripcion):
        """Genera el mensaje del recordatorio"""
        return f"""
Estimado usuario,

Le recordamos que su contrato de arrendamiento vencerá en {descripcion}.

Detalles del contrato:
- Inmueble: {info_contrato.get('inmueble', 'N/A')}
- Arrendatario: {info_contrato.get('arrendatario', 'N/A')}
- Fecha de vencimiento: {fecha_vigencia.strftime('%d/%m/%Y')}

Le recomendamos contactar al arrendatario para coordinar la renovación del contrato o los procedimientos de desalojo si es necesario.

Saludos cordiales,
Sistema Arrendify
        """.strip()

    def enviar_email_recordatorio(self, usuario, titulo, mensaje, info_contrato):
        """Envía email de recordatorio"""
        try:
            if not self.dry_run and usuario.email:
                self.stdout.write(f'Intentando enviar email a {usuario.email}')
                send_mail(
                    subject=titulo,
                    message=mensaje,
                    from_email=getattr(settings, 'DEFAULT_FROM_EMAIL', 'noreply@arrendify.com'),
                    recipient_list=[usuario.email],
                    fail_silently=False,
                )
                
                self.stdout.write(
                    self.style.SUCCESS(f'Email enviado exitosamente a {usuario.email}')
                )
            elif self.dry_run:
                self.stdout.write(
                    self.style.WARNING(f'[DRY-RUN] Se enviaría email a {usuario.email}')
                )
            else:
                self.stdout.write(
                    self.style.WARNING(f'Usuario {usuario.username} no tiene email configurado')
                )
        except Exception as e:
            self.stdout.write(
                self.style.ERROR(f'Error enviando email a {usuario.email}: {e}')
            )
            self.stdout.write(
                self.style.WARNING('Continuando con la creación de notificaciones...')
            )

    def parse_fecha(self, fecha_str):
        """Parsea una fecha desde string"""
        try:
            if isinstance(fecha_str, date):
                return fecha_str
            elif isinstance(fecha_str, str):
                # Intentar varios formatos
                formatos = ['%Y-%m-%d', '%d/%m/%Y', '%d-%m-%Y']
                for formato in formatos:
                    try:
                        return timezone.datetime.strptime(fecha_str, formato).date()
                    except ValueError:
                        continue
        except Exception:
            pass
        return None

    def calcular_fecha_vigencia(self, fecha_celebracion, duracion):
        """Calcula la fecha de vigencia basada en la duración"""
        try:
            # Extraer número de meses de la duración
            import re
            match = re.search(r'(\d+)', str(duracion))
            if match:
                meses = int(match.group(1))
                return fecha_celebracion + relativedelta(months=meses)
        except Exception:
            pass
        return None
