# -*- encoding: utf-8 -*-
"""
Comando de Django para verificar contratos próximos a vencer
y generar recordatorios automáticos por email y notificaciones internas
"""

from django.core.management.base import BaseCommand
from django.utils import timezone
from django.conf import settings
from django.contrib.auth.models import User
from django.db.models import Q
from datetime import date, timedelta
from dateutil.relativedelta import relativedelta
from decouple import config
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

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
        parser.add_argument(
            '--notify-email',
            type=str,
            help='Email del administrador para recibir resumen de ejecución',
        )

    def handle(self, *args, **options):
        self.dry_run = options['dry_run']
        self.force = options['force']
        self.notify_email = options.get('notify_email') or 'desarrolloarrendify@gmail.com'
        
        # Inicializar contadores de estadísticas
        self.stats = {
            'notificaciones_creadas': 0,
            'notificaciones_eliminadas': 0,
            'emails_enviados': 0,
            'contratos_procesados': 0,
            'errores': 0,
            'inicio': timezone.now(),
        }
        
        self.stdout.write(
            self.style.SUCCESS(f'Iniciando verificación de contratos - {self.stats["inicio"]}')
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
        
        self.stats['fin'] = timezone.now()
        self.stats['duracion'] = (self.stats['fin'] - self.stats['inicio']).total_seconds()
        
        self.stdout.write(
            self.style.SUCCESS('Verificación completada exitosamente')
        )
        
        # Enviar email de resumen si está configurado
        if self.notify_email and not self.dry_run:
            self.enviar_resumen_ejecucion()
        elif self.notify_email and self.dry_run:
            self.stdout.write(
                self.style.WARNING(f'[DRY-RUN] Se enviaría resumen a {self.notify_email}')
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
                self.stats['contratos_procesados'] += 1
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
                self.stats['errores'] += 1
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
                self.stats['contratos_procesados'] += 1
                self.stdout.write(f'Procesando contrato Fraterna {contrato.id} - Usuario: {contrato.user}')
                self.stdout.write(f'Fecha vigencia encontrada: {contrato.fecha_vigencia}')
                self.procesar_recordatorios_contrato(
                    contrato, contrato.fecha_vigencia, 'fraterna', contrato_fraterna=contrato
                )
            except Exception as e:
                self.stats['errores'] += 1
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
                self.stats['contratos_procesados'] += 1
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
                self.stats['errores'] += 1
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
                self.stats['contratos_procesados'] += 1
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
                self.stats['errores'] += 1
                self.stdout.write(
                    self.style.ERROR(f'Error procesando contrato Garza Sada {contrato.id}: {e}')
                )
    
    def procesar_recordatorios_contrato(self, contrato, fecha_vigencia, tipo_contrato, **kwargs):
        """Procesa los recordatorios para un contrato específico"""
        self.stdout.write(f'Procesando recordatorios para contrato {tipo_contrato} - Fecha vigencia: {fecha_vigencia}')
        
        hoy = date.today()
        self.stdout.write(f'Fecha actual: {hoy}')
        
        # Verificar si el contrato ya venció
        if fecha_vigencia < hoy:
            self.stdout.write(
                self.style.WARNING(
                    f'Contrato {contrato.id} ya venció ({fecha_vigencia}) - Eliminando todas las notificaciones'
                )
            )
            
            # 🗑️ ELIMINAR TODAS las notificaciones del contrato vencido
            if not self.dry_run:
                filtros_vencido = {
                    'tipo_contrato': tipo_contrato,
                    'fecha_vencimiento_contrato': fecha_vigencia,
                }
                filtros_vencido.update(kwargs)
                
                notificaciones_eliminadas = Notificacion.objects.filter(**filtros_vencido).delete()
                
                if notificaciones_eliminadas[0] > 0:
                    self.stats['notificaciones_eliminadas'] += notificaciones_eliminadas[0]
                    self.stdout.write(
                        self.style.SUCCESS(
                            f'🗑️ Eliminadas {notificaciones_eliminadas[0]} notificación(es) de contrato vencido'
                        )
                    )
                else:
                    self.stdout.write('ℹ️ No había notificaciones para eliminar')
            else:
                self.stdout.write('[DRY-RUN] Se eliminarían todas las notificaciones del contrato vencido')
            
            return
        
        # Calcular días restantes hasta vencimiento
        dias_restantes = (fecha_vigencia - hoy).days
        self.stdout.write(f'⏰ Días restantes hasta vencimiento: {dias_restantes}')
        
        # Calcular fechas de recordatorio
        fecha_3_meses = fecha_vigencia - relativedelta(months=3)
        fecha_2_meses = fecha_vigencia - relativedelta(months=2)
        fecha_1_mes = fecha_vigencia - relativedelta(months=1)
        
        self.stdout.write(f'Fechas recordatorio: 3m={fecha_3_meses}, 2m={fecha_2_meses}, 1m={fecha_1_mes}')
        
        # 🎯 DETERMINAR QUÉ NOTIFICACIÓN DEBE ESTAR ACTIVA según días restantes
        # ~90 días = 3 meses, ~60 días = 2 meses, ~30 días = 1 mes
        notificacion_actual = None
        notificaciones_incorrectas = []  # Todas las que NO deben existir (anteriores y futuras)
        
        if dias_restantes <= 30:
            # Falta 1 mes o menos → Solo notificación de 1 mes debe existir
            notificacion_actual = ('recordatorio_1_mes', fecha_1_mes, '1 mes')
            notificaciones_incorrectas = ['recordatorio_3_meses', 'recordatorio_2_meses']
            self.stdout.write('📍 Período: 1 mes o menos hasta vencimiento')
            
        elif dias_restantes <= 60:
            # Faltan entre 1-2 meses → Solo notificación de 2 meses debe existir
            notificacion_actual = ('recordatorio_2_meses', fecha_2_meses, '2 meses')
            notificaciones_incorrectas = ['recordatorio_3_meses', 'recordatorio_1_mes']  # Anterior Y futura
            self.stdout.write('📍 Período: Entre 1-2 meses hasta vencimiento')
            
        elif dias_restantes <= 90:
            # Faltan entre 2-3 meses → Solo notificación de 3 meses debe existir
            notificacion_actual = ('recordatorio_3_meses', fecha_3_meses, '3 meses')
            notificaciones_incorrectas = ['recordatorio_2_meses', 'recordatorio_1_mes']  # Futuras
            self.stdout.write('📍 Período: Entre 2-3 meses hasta vencimiento')
        else:
            # Faltan más de 3 meses → No debe existir ninguna notificación
            self.stdout.write('⏳ Faltan más de 3 meses, no es necesario crear notificación aún')
            
            # 🗑️ ELIMINAR cualquier notificación que exista (no debería haber ninguna)
            if not self.dry_run:
                filtros_base = {
                    'tipo_contrato': tipo_contrato,
                    'fecha_vencimiento_contrato': fecha_vigencia,
                }
                filtros_base.update(kwargs)
                
                todas_notificaciones = Notificacion.objects.filter(**filtros_base).delete()
                
                if todas_notificaciones[0] > 0:
                    self.stats['notificaciones_eliminadas'] += todas_notificaciones[0]
                    self.stdout.write(
                        self.style.SUCCESS(
                            f'🗑️ Eliminadas {todas_notificaciones[0]} notificación(es) prematuras (faltan >3 meses)'
                        )
                    )
            else:
                self.stdout.write('[DRY-RUN] Se eliminarían notificaciones prematuras si existieran')
            
            return
        
        if notificacion_actual:
            tipo_recordatorio, fecha_recordatorio, descripcion = notificacion_actual
            
            # 🗑️ ELIMINAR TODAS las notificaciones incorrectas (anteriores Y futuras)
            if notificaciones_incorrectas and not self.dry_run:
                filtros_base = {
                    'tipo_contrato': tipo_contrato,
                    'fecha_vencimiento_contrato': fecha_vigencia,
                }
                filtros_base.update(kwargs)
                
                for tipo_incorrecto in notificaciones_incorrectas:
                    notificaciones_eliminadas = Notificacion.objects.filter(
                        tipo_notificacion=tipo_incorrecto,
                        **filtros_base
                    ).delete()
                    
                    if notificaciones_eliminadas[0] > 0:
                        self.stats['notificaciones_eliminadas'] += notificaciones_eliminadas[0]
                        self.stdout.write(
                            self.style.SUCCESS(
                                f'🗑️ Eliminadas {notificaciones_eliminadas[0]} notificación(es) incorrectas: {tipo_incorrecto}'
                            )
                        )
            elif notificaciones_incorrectas and self.dry_run:
                self.stdout.write(f'[DRY-RUN] Se eliminarían notificaciones incorrectas: {", ".join(notificaciones_incorrectas)}')
            
            # ✅ CREAR la notificación del período actual (si no existe)
            self.stdout.write(f'✅ Creando notificación actual: {descripcion}')
            self.crear_recordatorio(
                contrato, fecha_vigencia, tipo_recordatorio, 
                tipo_contrato, descripcion, **kwargs
            )
    
    def crear_recordatorio(self, contrato, fecha_vigencia, tipo_recordatorio, 
                          tipo_contrato, descripcion, **kwargs):
        """Crea un recordatorio eliminando primero cualquier duplicado existente"""
        
        # Filtros para identificar la notificación específica
        filtros = {
            'tipo_notificacion': tipo_recordatorio,
            'tipo_contrato': tipo_contrato,
            'fecha_vencimiento_contrato': fecha_vigencia,
        }
        filtros.update(kwargs)
        
        # 🗑️ ELIMINAR cualquier notificación existente del mismo tipo para evitar duplicados
        if not self.dry_run:
            notificaciones_eliminadas = Notificacion.objects.filter(**filtros).delete()
            if notificaciones_eliminadas[0] > 0:
                self.stats['notificaciones_eliminadas'] += notificaciones_eliminadas[0]
                self.stdout.write(
                    self.style.WARNING(
                        f'🗑️ Eliminada(s) {notificaciones_eliminadas[0]} notificación(es) existente(s) de {tipo_recordatorio} para evitar duplicados'
                    )
                )
        elif Notificacion.objects.filter(**filtros).exists():
            self.stdout.write(
                self.style.WARNING(
                    f'[DRY-RUN] Se eliminaría notificación existente de {tipo_recordatorio} antes de crear nueva'
                )
            )
        
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
            self.stats['notificaciones_creadas'] += 1
            
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
                    # Para fraterna: intentar primero nombre_arrendatario (padre/tutor)
                    nombre_para_buscar = getattr(contrato.residente, 'nombre_arrendatario', None)
                    
                    # Si nombre_arrendatario está vacío, usar nombre_residente (estudiante)
                    if not nombre_para_buscar or nombre_para_buscar.strip() == '':
                        nombre_para_buscar = getattr(contrato.residente, 'nombre_residente', None)
                        self.stdout.write(f'ℹ️ Usando nombre_residente: {nombre_para_buscar}')
                    else:
                        self.stdout.write(f'ℹ️ Usando nombre_arrendatario: {nombre_para_buscar}')
                    
                    if nombre_para_buscar and nombre_para_buscar.strip() != '':
                        info['arrendatario'] = nombre_para_buscar.strip()
                        info['usuario'] = self.buscar_usuario_por_nombre(nombre_para_buscar.strip())
                    else:
                        # Último fallback
                        self.stdout.write(self.style.WARNING('⚠️ No se encontró nombre válido en residente'))
                        info['arrendatario'] = f'Residente ID {contrato.residente.id}'
                        info['usuario'] = contrato.user
                else:
                    info['arrendatario'] = 'N/A'
                    info['usuario'] = contrato.user  # Fallback al usuario del contrato
                
            elif tipo_contrato == 'semillero':
                info['inmueble'] = f"Propiedad {contrato.id}"
                if contrato.arrendatario:
                    # Para semillero: usar nombre_arrendatario del arrendatario
                    nombre_para_buscar = getattr(contrato.arrendatario, 'nombre_arrendatario', None)
                    
                    # Verificar que no esté vacío
                    if not nombre_para_buscar or nombre_para_buscar.strip() == '':
                        # Intentar nombre_empresa_pm como alternativa
                        nombre_para_buscar = getattr(contrato.arrendatario, 'nombre_empresa_pm', None)
                        if nombre_para_buscar:
                            self.stdout.write(f'ℹ️ Semillero - Usando nombre_empresa_pm: {nombre_para_buscar}')
                    else:
                        self.stdout.write(f'ℹ️ Semillero - Usando nombre_arrendatario: {nombre_para_buscar}')
                    
                    if nombre_para_buscar and nombre_para_buscar.strip() != '':
                        info['arrendatario'] = nombre_para_buscar.strip()
                        info['usuario'] = self.buscar_usuario_por_nombre(nombre_para_buscar.strip())
                    else:
                        self.stdout.write(self.style.WARNING('⚠️ Semillero - No se encontró nombre válido'))
                        info['arrendatario'] = f'Arrendatario ID {contrato.arrendatario.id}'
                        info['usuario'] = contrato.user
                else:
                    info['arrendatario'] = 'N/A'
                    info['usuario'] = contrato.user  # Fallback al usuario del contrato
                
            elif tipo_contrato == 'garzasada':
                info['inmueble'] = f"Depto {contrato.no_depa or 'N/A'}"
                if contrato.arrendatario:
                    # Para garzasada: usar nombre_arrendatario del arrendatario
                    nombre_para_buscar = getattr(contrato.arrendatario, 'nombre_arrendatario', None)
                    
                    # Verificar que no esté vacío
                    if not nombre_para_buscar or nombre_para_buscar.strip() == '':
                        # Intentar nombre_empresa_pm como alternativa
                        nombre_para_buscar = getattr(contrato.arrendatario, 'nombre_empresa_pm', None)
                        if nombre_para_buscar:
                            self.stdout.write(f'ℹ️ GarzaSada - Usando nombre_empresa_pm: {nombre_para_buscar}')
                    else:
                        self.stdout.write(f'ℹ️ GarzaSada - Usando nombre_arrendatario: {nombre_para_buscar}')
                    
                    if nombre_para_buscar and nombre_para_buscar.strip() != '':
                        info['arrendatario'] = nombre_para_buscar.strip()
                        info['usuario'] = self.buscar_usuario_por_nombre(nombre_para_buscar.strip())
                    else:
                        self.stdout.write(self.style.WARNING('⚠️ GarzaSada - No se encontró nombre válido'))
                        info['arrendatario'] = f'Arrendatario ID {contrato.arrendatario.id}'
                        info['usuario'] = contrato.user
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
        return f"""Estimado usuario,<br><br>Le recordamos que su contrato de arrendamiento vencerá en <strong>{descripcion}</strong>.<br><br><strong>Detalles del contrato:</strong><br>• Inmueble: {info_contrato.get('inmueble', 'N/A')}<br>• Arrendatario: {info_contrato.get('arrendatario', 'N/A')}<br>• Fecha de vencimiento: <span style="color: #dc3545; font-weight: bold;">{fecha_vigencia.strftime('%d/%m/%Y')}</span><br><br>Le recomendamos contactar al arrendatario para coordinar la renovación del contrato o los procedimientos de desalojo si es necesario.<br><br>Saludos cordiales,<br><strong>Sistema Arrendify</strong>"""

    def enviar_email_recordatorio(self, usuario, titulo, mensaje, info_contrato):
        """Envía email de recordatorio usando smtplib"""
        try:
            if not self.dry_run and usuario.email:
                self.stdout.write(f'Intentando enviar email a {usuario.email}')
                
                # Configuración SMTP desde .env
                smtp_server = 'mail.arrendify.com'
                smtp_port = 587
                smtp_username = config('mine_smtp_u')
                smtp_password = config('mine_smtp_pw')
                remitente = 'notificaciones@arrendify.com'
                
                # Crear mensaje
                msg = MIMEMultipart()
                msg['From'] = remitente
                msg['To'] = usuario.email
                msg['Subject'] = titulo
                msg.attach(MIMEText(mensaje, 'plain'))
                
                # Enviar email
                with smtplib.SMTP(smtp_server, smtp_port) as server:
                    server.starttls()
                    server.login(smtp_username, smtp_password)
                    server.sendmail(remitente, usuario.email, msg.as_string())
                
                self.stats['emails_enviados'] += 1
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

    def enviar_resumen_ejecucion(self):
        """Envía email con resumen de la ejecución del comando usando smtplib"""
        try:
            duracion_minutos = round(self.stats['duracion'] / 60, 2)
            
            asunto = f"✅ Verificación de Contratos Completada - {self.stats['inicio'].strftime('%d/%m/%Y %H:%M')}"
            
            mensaje = f"""
╔══════════════════════════════════════════════════════════════╗
║     RESUMEN DE VERIFICACIÓN DE CONTRATOS PRÓXIMOS A VENCER   ║
╚══════════════════════════════════════════════════════════════╝

📅 Fecha de ejecución: {self.stats['inicio'].strftime('%d/%m/%Y %H:%M:%S')}
⏱️  Duración: {duracion_minutos} minutos ({self.stats['duracion']} segundos)

📊 ESTADÍSTICAS:
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  📝 Contratos procesados:        {self.stats['contratos_procesados']}
  ✅ Notificaciones creadas:      {self.stats['notificaciones_creadas']}
  🗑️  Notificaciones eliminadas:   {self.stats['notificaciones_eliminadas']}
  📧 Emails enviados:              {self.stats['emails_enviados']}
  ❌ Errores encontrados:          {self.stats['errores']}

{'⚠️  MODO DRY-RUN ACTIVADO - No se realizaron cambios reales' if self.dry_run else '✅ Ejecución completada exitosamente'}

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

🔔 Este es un mensaje automático del sistema de gestión de contratos.
   Servidor: {config('SERVER', default='EC2 Production')}
   
Para más detalles, revisa los logs del servidor.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Sistema Arrendify - Gestión de Contratos
"""
            
            # Configuración SMTP desde .env
            smtp_server = 'mail.arrendify.com'
            smtp_port = 587
            smtp_username = config('mine_smtp_u')
            smtp_password = config('mine_smtp_pw')
            remitente = 'notificaciones@arrendify.com'
            
            # Crear mensaje
            msg = MIMEMultipart()
            msg['From'] = remitente
            msg['To'] = self.notify_email
            msg['Subject'] = asunto
            msg.attach(MIMEText(mensaje, 'plain'))
            
            # Enviar email
            with smtplib.SMTP(smtp_server, smtp_port) as server:
                server.starttls()
                server.login(smtp_username, smtp_password)
                server.sendmail(remitente, self.notify_email, msg.as_string())
            
            self.stdout.write(
                self.style.SUCCESS(f'📧 Resumen de ejecución enviado a {self.notify_email}')
            )
            
        except Exception as e:
            self.stdout.write(
                self.style.ERROR(f'❌ Error enviando resumen de ejecución: {e}')
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
