"""
HardwareController - Drivers de Hardware con Comunicación Serial Robusta.
Gestión de SimBank y Módems con reintentos automáticos y manejo de errores.
"""
import serial
import time
import subprocess
import threading
import logging
from typing import Optional, Dict, Tuple
from functools import wraps


def retry_serial(max_retries=3):
    """
    Decorador para reintentar automáticamente operaciones seriales fallidas.
    
    Args:
        max_retries: Número máximo de reintentos
        
    Usage:
        @retry_serial(max_retries=3)
        def send_command(port, cmd):
            ...
    """
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            last_exception = None
            
            for attempt in range(1, max_retries + 1):
                try:
                    return func(*args, **kwargs)
                except serial.SerialException as e:
                    last_exception = e
                    if attempt < max_retries:
                        wait_time = 2 ** attempt  # Espera exponencial: 2s, 4s, 8s
                        logging.warning(f"  ⚠️  Intento {attempt}/{max_retries} falló: {e}")
                        logging.info(f"     Reintentando en {wait_time}s...")
                        time.sleep(wait_time)
                    else:
                        logging.error(f"  ❌ Todos los intentos fallaron después de {max_retries} reintentos")
                except Exception as e:
                    # Para errores no seriales, fallar inmediatamente
                    logging.error(f"  ❌ Error no recuperable: {e}")
                    raise
            
            # Si llegamos aquí, todos los reintentos fallaron
            raise last_exception
        
        return wrapper
    return decorator


class SimController:
    """
    Controlador de hardware para SimBank y Módems.
    Gestiona comunicación serial con reintentos y sincronización.
    """
    
    # Locks estáticos para sincronizar acceso a puertos de control (pool)
    # Clave: puerto COM, Valor: threading.Lock
    pool_locks: Dict[str, threading.Lock] = {}
    _locks_init_lock = threading.Lock()  # Lock para inicializar pool_locks thread-safe
    
    # Lock global para serializar comandos AT+SWIT (evitar envíos simultáneos)
    _swit_global_lock = threading.Lock()
    _last_swit_time = 0  # Timestamp del último envío AT+SWIT
    
    def __init__(self, config_manager, logger=None):
        """
        Inicializa el controlador con configuración.
        
        Args:
            config_manager: Instancia de ConfigManager con la configuración
            logger: Logger opcional para registro de eventos
        """
        self.config = config_manager.config_data
        self.baudrate = self.config.get('baudrate', 115200)
        self.at_timeout = self.config.get('at_timeout', 3)
        self.logger = logger or logging.getLogger(__name__)
        
        # Inicializar locks para todos los puertos de control
        self._initialize_pool_locks()
    
    def _initialize_pool_locks(self):
        """Inicializa los locks para todos los puertos de control (pool)."""
        with SimController._locks_init_lock:
            for bank in self.config.get('simbanks', []):
                control_port = bank.get('control_port')
                if control_port and control_port not in SimController.pool_locks:
                    SimController.pool_locks[control_port] = threading.Lock()
                    self.logger.debug(f"🔒 Lock creado para puerto de control: {control_port}")
    
    @staticmethod
    def _get_pool_lock(pool_port: str) -> threading.Lock:
        """
        Obtiene o crea el lock para un puerto de control.
        
        Args:
            pool_port: Puerto COM del SimBank
            
        Returns:
            threading.Lock para el puerto
        """
        with SimController._locks_init_lock:
            if pool_port not in SimController.pool_locks:
                SimController.pool_locks[pool_port] = threading.Lock()
            return SimController.pool_locks[pool_port]
    
    def _send_at_command(self, ser: serial.Serial, command: str, expected_ok: bool = True, 
                        is_critical: bool = True, port_name: str = None) -> tuple:
        """
        Envía comando AT y loggea el comando + respuesta.
        
        Args:
            ser: Objeto serial abierto
            command: Comando AT a enviar (sin \r\n)
            expected_ok: Si se espera respuesta con OK
            is_critical: Si falla, es ERROR (True) o WARNING (False)
            port_name: Nombre del puerto para logs
            
        Returns:
            (success: bool, response: str)
        """
        port = port_name or (ser.port if hasattr(ser, 'port') else 'UNKNOWN')
        
        try:
            ser.flushInput()
            ser.flushOutput()
            
            # Log del comando enviado
            self.logger.debug(f"[{port}] 📤 AT: {command}")
            
            # Enviar comando
            ser.write(f"{command}\r\n".encode('ascii'))
            time.sleep(0.5)
            
            # Leer respuesta
            response = ser.read(200).decode('utf-8', errors='ignore').strip()
            
            # Log de la respuesta
            self.logger.debug(f"[{port}] 📥 RESP: {response}")
            
            # Verificar si es exitoso
            success = 'OK' in response if expected_ok else True
            
            # Log del resultado
            if expected_ok:
                if success:
                    self.logger.debug(f"[{port}] ✅ {command} -> OK")
                else:
                    if is_critical:
                        self.logger.error(f"[{port}] ❌ {command} -> SIN OK: {response}")
                    else:
                        self.logger.warning(f"[{port}] ⚠️  {command} -> SIN OK: {response}")
            
            return success, response
            
        except Exception as e:
            self.logger.error(f"[{port}] ❌ Error enviando {command}: {e}")
            return False, str(e)
    
    def initialize_simbank(self, pool_port: str) -> bool:
        """
        Inicializa un SimBank (UNA VEZ POR POOL_COM).
        
        Secuencia:
        1. AT+CWSIM - Verificar que está listo
        2. AT+NEXT00 - Reset de todos los canales (opcional si CWSIM falla)
        3. Si ambos fallan: AT+SWIT00-0000 como fallback
        
        Args:
            pool_port: Puerto COM del SimBank (ej: 'COM19')
            
        Returns:
            True si la inicialización fue exitosa
        """
        lock = self._get_pool_lock(pool_port)
        
        with lock:
            ser = None
            try:
                self.logger.info(f"🔧 Inicializando SimBank {pool_port}...")
                
                ser = serial.Serial(
                    port=pool_port,
                    baudrate=self.baudrate,
                    timeout=3
                )
                
                # PASO 1: AT+CWSIM (verificar listo)
                success_cwsim, resp_cwsim = self._send_at_command(
                    ser, 'AT+CWSIM', 
                    expected_ok=False,  # Respuesta especial: CWSIM OK o SWSIM OK
                    is_critical=False,
                    port_name=pool_port
                )
                
                # Verificar respuesta específica
                is_ready = 'CWSIM OK' in resp_cwsim or 'SWSIM OK' in resp_cwsim
                
                if is_ready:
                    self.logger.info(f"  ✅ {pool_port}: SimBank listo (AT+CWSIM OK)")
                    return True
                else:
                    self.logger.warning(f"  ⚠️  {pool_port}: AT+CWSIM no respondió correctamente")
                
                # PASO 2: AT+NEXT00 (reset de canales)
                self.logger.info(f"  🔄 {pool_port}: Intentando AT+NEXT00 (reset)...")
                success_next, resp_next = self._send_at_command(
                    ser, 'AT+NEXT00',
                    expected_ok=False,  # Respuesta especial: SWSIM OK
                    is_critical=False,
                    port_name=pool_port
                )
                
                if 'SWSIM OK' in resp_next:
                    self.logger.info(f"  ✅ {pool_port}: Reset exitoso (AT+NEXT00 OK)")
                    return True
                else:
                    self.logger.warning(f"  ⚠️  {pool_port}: AT+NEXT00 no respondió correctamente")
                
                # PASO 3: FALLBACK - AT+SWIT00-0000 (desconectar todos)
                self.logger.info(f"  🔄 {pool_port}: Fallback con AT+SWIT00-0000...")
                success_swit, resp_swit = self._send_at_command(
                    ser, 'AT+SWIT00-0000',
                    expected_ok=True,
                    is_critical=False,
                    port_name=pool_port
                )
                
                if success_swit:
                    self.logger.info(f"  ✅ {pool_port}: Inicializado con fallback (AT+SWIT00-0000)")
                    return True
                else:
                    self.logger.error(f"  ❌ {pool_port}: FALLO EN INICIALIZACIÓN (todos los intentos)")
                    return False
                
            except Exception as e:
                self.logger.error(f"  ❌ {pool_port}: Error en inicialización: {e}")
                return False
            finally:
                if ser and ser.is_open:
                    # Limpiar buffers antes de cerrar
                    try:
                        ser.reset_input_buffer()   # Flush input buffer
                        ser.reset_output_buffer()  # Flush output buffer
                        self.logger.debug(f"🧹 [{pool_port}] Buffers limpiados antes de cerrar")
                    except Exception as e:
                        self.logger.warning(f"⚠️  [{pool_port}] Error al limpiar buffers: {e}")
                    ser.close()
    
    @retry_serial(max_retries=3)
    def switch_sim(self, pool_port: str, col: str, row: int, modem_port: str = None) -> dict:
        """
        Conmuta la SIM activa en el SimBank usando AT+SWIT.
        Serializa envíos con retardo de 1s para evitar colisiones.
        Reintenta hasta 4 veces si falla.
        
        Formato estricto: AT+SWITCC-FFFF
        - CC: Columna (01-08) con padding de ceros
        - FFFF: Fila (0001-0016) con padding de ceros
        
        Args:
            pool_port: Puerto COM del SimBank (ej: 'COM19')
            col: Columna como string (ej: '01', '08')
            row: Fila como entero (1-16)
            modem_port: Puerto COM del módem/slot (ej: 'COM10') - para logs
            
        Returns:
            Dict con: {'success': bool, 'command': str, 'response': str, 'attempts': int}
        """
        # SERIALIZACIÓN GLOBAL: Asegurar 1 segundo entre envíos de AT+SWIT
        with SimController._swit_global_lock:
            elapsed = time.time() - SimController._last_swit_time
            if elapsed < 1.0:
                wait_time = 1.0 - elapsed
                self.logger.debug(f"⏸️  Esperando {wait_time:.2f}s antes de enviar AT+SWIT (serialización)")
                time.sleep(wait_time)
            SimController._last_swit_time = time.time()
        
        # Obtener lock del puerto
        lock = self._get_pool_lock(pool_port)
        
        cmd = f"AT+SWIT{col}-{row:04d}"
        max_retries = 4
        
        with lock:
            ser = None
            try:
                # Abrir puerto de control
                ser = serial.Serial(
                    port=pool_port,
                    baudrate=self.baudrate,
                    timeout=self.at_timeout
                )
                
                # Intentar comando hasta 4 veces
                for attempt in range(1, max_retries + 1):
                    # Enviar comando usando método unificado
                    success, response = self._send_at_command(
                        ser, cmd,
                        expected_ok=True,
                        is_critical=False,  # WARNING si falla (puede ser reintentado)
                        port_name=pool_port
                    )
                    
                    if success:
                        if modem_port:
                            self.logger.info(f"  ✅ SWIT exitoso: [Slot {modem_port}] via Pool {pool_port} -> Col {col}, Fila {row:04d} (intento {attempt})")
                        else:
                            self.logger.info(f"  ✅ SWIT exitoso: {pool_port} -> Col {col}, Fila {row:04d} (intento {attempt})")
                        # Esperar tiempo adicional DENTRO del lock para asegurar cambio físico
                        time.sleep(2)
                        
                        return {
                            'success': True,
                            'command': cmd,
                            'response': response,
                            'attempts': attempt
                        }
                    else:
                        if modem_port:
                            self.logger.warning(f"  ⚠️  SWIT falló (intento {attempt}/{max_retries}): [Slot {modem_port}] via Pool {pool_port} -> {cmd}")
                        else:
                            self.logger.warning(f"  ⚠️  SWIT falló (intento {attempt}/{max_retries}): {pool_port} -> {cmd}")
                        self.logger.warning(f"  📡 Respuesta: {response}")
                        
                        if attempt < max_retries:
                            self.logger.info(f"  ⏳ Esperando 5s antes de reintentar...")
                            time.sleep(5)
                
                # Si llegó aquí, todos los intentos fallaron
                if modem_port:
                    self.logger.error(f"  ❌ SWIT falló después de {max_retries} intentos: [Slot {modem_port}] via Pool {pool_port} -> {cmd}")
                else:
                    self.logger.error(f"  ❌ SWIT falló después de {max_retries} intentos: {pool_port} -> {cmd}")
                return {
                    'success': False,
                    'command': cmd,
                    'response': response if 'response' in locals() else 'No response',
                    'attempts': max_retries
                }
                
            except serial.SerialException as e:
                if modem_port:
                    self.logger.error(f"  ❌ Error serial en [Slot {modem_port}] via Pool {pool_port}: {e}")
                else:
                    self.logger.error(f"  ❌ Error serial en {pool_port}: {e}")
                return {
                    'success': False,
                    'command': cmd,
                    'response': f'SerialException: {e}',
                    'attempts': 0
                }
            except Exception as e:
                self.logger.error(f"  ❌ Error inesperado en switch_sim: {e}")
                return {
                    'success': False,
                    'command': cmd,
                    'response': f'Exception: {e}',
                    'attempts': 0
                }
            finally:
                if ser and ser.is_open:
                    # Limpiar buffers antes de cerrar
                    try:
                        ser.reset_input_buffer()   # Flush input buffer
                        ser.reset_output_buffer()  # Flush output buffer
                        self.logger.debug(f"🧹 [{pool_port}] Buffers limpiados antes de cerrar")
                    except Exception as e:
                        self.logger.warning(f"⚠️  [{pool_port}] Error al limpiar buffers: {e}")
                    ser.close()
    
    def reboot_modem(self, serial_obj: serial.Serial, model: str) -> bool:
        """
        Reinicia la radio del módem según el modelo.
        
        IMPORTANTE: Recibe un objeto serial YA ABIERTO.
        
        Secuencias:
        - EC25: AT+CFUN=0 -> Sleep 10s -> AT+CFUN=1
        - UC20: AT+CFUN=1,1 -> Sleep 10s
        
        Args:
            serial_obj: Objeto serial.Serial ya abierto
            model: Modelo del módem ('EC25', 'UC20', etc.)
            
        Returns:
            True si el reinicio fue exitoso
        """
        try:
            if not serial_obj.is_open:
                port = serial_obj.port if hasattr(serial_obj, 'port') else 'UNKNOWN'
                self.logger.warning(f"[{port}] ⚠️  Puerto serial no está abierto")
                return False
            
            port = serial_obj.port
            
            # Limpiar buffers
            serial_obj.flushInput()
            serial_obj.flushOutput()
            
            if model == 'EC25':
                # PASO 1: Modo avión (apagar radio)
                self._send_at_command(serial_obj, 'AT+CFUN=0', expected_ok=True, is_critical=False, port_name=port)
                
                # CRÍTICO: Esperar 10 segundos (descarga de capacitores - Módulo 1)
                self.logger.info(f"[{port}] ⏱️  Esperando 10s (descarga capacitores EC25)...")
                time.sleep(10)
                
                # PASO 2: Encender radio
                success, _ = self._send_at_command(serial_obj, 'AT+CFUN=1', expected_ok=True, is_critical=False, port_name=port)
                
                self.logger.info(f"[{port}] ✅ Reinicio EC25 completado")
                return True
                
            elif model == 'UC20':
                # Reset directo con reinicio físico
                self._send_at_command(serial_obj, 'AT+CFUN=1,1', expected_ok=True, is_critical=False, port_name=port)
                
                # Esperar reinicio físico del módem
                self.logger.info(f"[{port}] ⏱️  Esperando 10s (reinicio UC20)...")
                time.sleep(10)
                
                self.logger.info(f"[{port}] ✅ Reinicio UC20 completado")
            
            else:
                self.logger.warning(f"[{port}] ⚠️  Modelo desconocido: {model}, usando secuencia genérica")
                self._send_at_command(serial_obj, 'AT+CFUN=1,1', expected_ok=True, is_critical=False, port_name=port)
                time.sleep(10)
            
            return True
            
        except Exception as e:
            port = serial_obj.port if hasattr(serial_obj, 'port') else 'UNKNOWN'
            self.logger.error(f"[{port}] ❌ Error en reboot_modem: {e}")
            return False
    
    def wait_for_signal(self, serial_obj: serial.Serial, max_wait: int = 60) -> Tuple[bool, str]:
        """
        Espera a que el módem se registre en la red.
        
        IMPORTANTE: Recibe un objeto serial YA ABIERTO.
        
        Verifica AT+CREG? hasta obtener registro (creg = 1 o 5).
        
        Args:
            serial_obj: Objeto serial.Serial ya abierto
            max_wait: Tiempo máximo de espera en segundos
            
        Returns:
            Tupla (éxito: bool, estado_creg: str)
        """
        try:
            if not serial_obj.is_open:
                port = serial_obj.port if hasattr(serial_obj, 'port') else 'UNKNOWN'
                self.logger.warning(f"[{port}] ⚠️  Puerto serial no está abierto")
                return False, 'CLOSED'
            
            port = serial_obj.port
            self.logger.info(f"[{port}] 📡 Esperando registro en red (max {max_wait}s)...")
            
            start_time = time.time()
            attempt = 0
            
            while (time.time() - start_time) < max_wait:
                attempt += 1
                
                try:
                    # Limpiar buffer
                    serial_obj.flushInput()
                    
                    # Consultar estado de registro
                    serial_obj.write(b'AT+CREG?\r\n')
                    time.sleep(1)
                    
                    response = serial_obj.read(200).decode('utf-8', errors='ignore')
                    
                    # Buscar patrón +CREG: n,stat
                    import re
                    match = re.search(r'\+CREG:\s*\d+,(\d+)', response)
                    
                    if match:
                        creg_status = match.group(1)
                        
                        # 1 = Home network, 5 = Roaming
                        if creg_status in ['1', '5']:
                            network_type = "Home" if creg_status == '1' else "Roaming"
                            self.logger.info(f"[{port}] ✅ Registrado en red ({network_type}) - CREG={creg_status}")
                            return True, creg_status
                        
                        # 0 = Not registered, 2 = Searching, 3 = Denied
                        elif creg_status == '3':
                            self.logger.warning(f"[{port}] ❌ Registro DENEGADO - CREG={creg_status}")
                            return False, creg_status
                        
                        # Seguir esperando
                        if attempt % 5 == 0:  # Log cada 5 intentos
                            self.logger.info(f"[{port}] ⏳ Buscando red... CREG={creg_status} ({int(time.time() - start_time)}s)")
                    
                    time.sleep(3)  # Esperar antes del siguiente intento
                    
                except Exception as e:
                    self.logger.warning(f"[{port}] ⚠️  Error en lectura CREG: {e}")
                    time.sleep(3)
            
            # Timeout alcanzado
            self.logger.warning(f"[{port}] ⏰ Timeout alcanzado ({max_wait}s) sin registro")
            return False, 'TIMEOUT'
            
        except Exception as e:
            port = serial_obj.port if hasattr(serial_obj, 'port') else 'UNKNOWN'
            self.logger.error(f"[{port}] ❌ Error en wait_for_signal: {e}")
            return False, 'ERROR'
    
    def check_creg_with_serial(self, serial_obj: serial.Serial) -> str:
        """
        Verifica el estado actual de CREG usando un serial ya abierto.
        
        Args:
            serial_obj: Objeto serial.Serial ya abierto
            
        Returns:
            Estado CREG como string ('1', '5', '0', '2', '3') o 'ERROR'
        """
        try:
            if not serial_obj.is_open:
                return 'ERROR'
            
            port = serial_obj.port if hasattr(serial_obj, 'port') else 'UNKNOWN'
            
            # Usar método unificado (no es crítico, solo consulta)
            success, response = self._send_at_command(
                serial_obj, 'AT+CREG?',
                expected_ok=False,  # No siempre tiene OK, solo respuesta
                is_critical=False,
                port_name=port
            )
            
            # Buscar patrón +CREG: n,stat
            import re
            match = re.search(r'\+CREG:\s*\d+,(\d+)', response)
            
            if match:
                return match.group(1)
            
            return 'ERROR'
            
        except Exception as e:
            return 'ERROR'
    
    def verify_sim_identity(self, serial_obj: serial.Serial) -> dict:
        """
        Verifica la identidad real del SIM en el módem.
        Lee ICCID (CCID) del SIM físicamente presente.
        
        Args:
            serial_obj: Objeto serial.Serial ya abierto
            
        Returns:
            {'ccid': str, 'success': bool}
        """
        try:
            if not serial_obj.is_open:
                return {'ccid': None, 'success': False}
            
            port = serial_obj.port if hasattr(serial_obj, 'port') else 'UNKNOWN'
            
            # Usar método unificado
            success, response = self._send_at_command(
                serial_obj, 'AT+CCID',
                expected_ok=False,  # Respuesta tiene ICCID, no necesariamente OK
                is_critical=False,
                port_name=port
            )
            
            # Buscar ICCID (19-20 dígitos)
            import re
            match = re.search(r'(\d{19,20})', response)
            
            if match:
                return {'ccid': match.group(1), 'success': True}
            
            return {'ccid': None, 'success': False}
            
        except Exception as e:
            self.logger.error(f"Error verificando identidad SIM: {e}")
            return {'ccid': None, 'success': False}
    
    def check_creg_status(self, modem_port: str) -> str:
        """
        Verifica el estado actual de CREG de un módem sin esperar.
        
        Args:
            modem_port: Puerto COM del módem (ej: 'COM6')
            
        Returns:
            Estado CREG como string ('1', '5', '0', '2', '3') o 'ERROR'
        """
        ser = None
        try:
            # Abrir puerto del módem
            ser = serial.Serial(
                port=modem_port,
                baudrate=self.baudrate,
                timeout=2
            )
            
            # Limpiar buffer
            ser.flushInput()
            ser.flushOutput()
            
            # Consultar CREG
            ser.write(b'AT+CREG?\r\n')
            time.sleep(0.5)
            
            response = ser.read(200).decode('utf-8', errors='ignore')
            
            # Buscar patrón +CREG: n,stat
            import re
            match = re.search(r'\+CREG:\s*\d+,(\d+)', response)
            
            if match:
                return match.group(1)
            
            return 'ERROR'
            
        except Exception as e:
            return 'ERROR'
        finally:
            if ser and ser.is_open:
                # Limpiar buffers antes de cerrar
                try:
                    ser.reset_input_buffer()   # Flush input buffer
                    ser.reset_output_buffer()  # Flush output buffer
                except Exception:
                    pass  # Ignorar errores en limpieza
                ser.close()
    
    def kill_simclient(self) -> bool:
        """
        Termina todos los procesos HeroSMS-Partners.exe y verifica el cierre.
        
        Protocolo del Módulo 3: PASO 1 - Limpieza de Entorno.
        
        Returns:
            True si el proceso fue terminado y verificado
        """
        try:
            from datetime import datetime
            start_time = datetime.now().strftime('%H:%M:%S.%f')[:-3]
            self.logger.info(f"🔪 [{start_time}] Terminando procesos HeroSMS-Partners.exe...")
            
            # Ejecutar taskkill con /F (forzar) y /IM (image name)
            result = subprocess.run(
                ['taskkill', '/IM', 'HeroSMS-Partners.exe', '/F'],
                capture_output=True,
                text=True,
                timeout=10
            )
            
            # taskkill retorna 0 si encuentra y mata procesos
            # retorna 128 si no encuentra el proceso (también es válido)
            kill_time = datetime.now().strftime('%H:%M:%S.%f')[:-3]
            if result.returncode == 0:
                self.logger.info(f"  ✅ [{kill_time}] HeroSMS-Partners.exe terminado")
            elif result.returncode == 128:
                self.logger.info(f"  ℹ️  [{kill_time}] HeroSMS-Partners.exe no estaba ejecutándose")
            else:
                self.logger.warning(f"  ⚠️  [{kill_time}] taskkill retornó código: {result.returncode}")
                self.logger.warning(f"     stdout: {result.stdout.strip()}")
                self.logger.warning(f"     stderr: {result.stderr.strip()}")
            
            # VERIFICAR que el proceso realmente se cerró
            self.logger.info("  🔍 Verificando cierre de HeroSMS-Partners.exe...")
            max_attempts = 10
            for attempt in range(max_attempts):
                # Buscar si aún existe el proceso
                check = subprocess.run(
                    ['tasklist', '/FI', 'IMAGENAME eq HeroSMS-Partners.exe'],
                    capture_output=True,
                    text=True,
                    timeout=5
                )
                
                if 'HeroSMS-Partners.exe' not in check.stdout:
                    self.logger.info(f"  ✅ Cierre verificado (intento {attempt + 1})")
                    return True
                
                if attempt < max_attempts - 1:
                    self.logger.info(f"  ⏳ HeroSMS-Partners.exe aún activo, esperando... ({attempt + 1}/{max_attempts})")
                    time.sleep(1)
            
            self.logger.warning("  ⚠️  HeroSMS-Partners.exe no se cerró después de 10 intentos")
            return False
                
        except subprocess.TimeoutExpired:
            self.logger.warning("  ⚠️  Timeout al ejecutar taskkill")
            return False
        except FileNotFoundError:
            self.logger.error("  ❌ taskkill.exe no encontrado (¿no es Windows?)")
            return False
        except Exception as e:
            self.logger.error(f"  ❌ Error al ejecutar taskkill: {e}")
            return False
    
    def detect_model(self, serial_obj: serial.Serial) -> str:
        """
        Detecta el modelo del módem usando ATI.
        
        Args:
            serial_obj: Objeto serial.Serial ya abierto
            
        Returns:
            Modelo detectado ('EC25', 'UC20', 'UNKNOWN')
        """
        try:
            if not serial_obj.is_open:
                return 'UNKNOWN'
            
            # Limpiar buffer
            serial_obj.flushInput()
            serial_obj.flushOutput()
            
            # Enviar ATI
            serial_obj.write(b'ATI\r\n')
            time.sleep(1)
            
            response = serial_obj.read(300).decode('utf-8', errors='ignore')
            
            if 'EC25' in response:
                return 'EC25'
            elif 'UC20' in response:
                return 'UC20'
            
            return 'UNKNOWN'
            
        except Exception as e:
            print(f"  ⚠️  Error detectando modelo: {e}")
            return 'UNKNOWN'
