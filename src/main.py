"""
Main - Orquestador Principal del Sistema mp_simclient.
Arquitectura "Barrier": Cambio paralelo de todos los módems, luego lanzamiento único de SimClient.
Soporta temporizadores individuales por puerto basados en sim_intento_operativo.
"""

import os
import sys
import time
import signal
import argparse
import serial
import subprocess
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta
from typing import Dict, Any, List

# Agregar src al path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from config.config_manager import ConfigManager
from data_manager import DataManager
from slot_logic import SlotManager
from hardware_controller import SimController
from logger_config import setup_logger, log_system_info, log_config_summary
from ccid_analyzer import CCIDAnalyzer
from utils.banner import print_startup_banner


class PortState:
    """
    Gestiona el estado de un puerto durante el monitoreo.
    Estados: waiting_registration, released, failed
    """

    def __init__(self, port: str):
        self.port = port
        self.current_sim = None
        self.state = "waiting_registration"  # waiting_registration | released | failed
        self.switch_time = None  # Cuándo se hizo el último switch/reboot
        self.last_monitor_time = None  # Timestamp del último monitoreo CREG
        self.reboot_attempted = False
        self.serial_obj = None  # Objeto serial si Python lo tiene abierto
        self.is_changing_sim = (
            False  # Flag para indicar que está cambiando SIM en thread
        )
        self.lock = threading.Lock()

    def start_monitoring(self, sim_info: dict):
        """Inicia monitoreo para una nueva SIM."""
        with self.lock:
            self.current_sim = sim_info
            self.switch_time = datetime.now()
            self.state = "waiting_registration"
            self.reboot_attempted = False
            # NO borrar serial_obj - mantener el serial abierto

    def mark_released(self):
        """
        Marca el puerto como liberado a SimClient.
        Realiza limpieza completa del buffer serial antes de cerrar.
        """
        with self.lock:
            self.state = "released"
            if self.serial_obj and self.serial_obj.is_open:
                try:
                    # LIMPIEZA COMPLETA antes de cerrar para SimClient

                    # 1. Limpiar comandos AT pendientes
                    self.serial_obj.write(b"AT\r\n")
                    time.sleep(0.1)
                    self.serial_obj.read(100)  # Descartar respuesta

                    # 2. Resetear estado de eco
                    self.serial_obj.write(b"ATE0\r\n")  # Desactivar echo
                    time.sleep(0.1)
                    self.serial_obj.read(100)  # Descartar respuesta

                    # 3. Flush de buffers input/output
                    self.serial_obj.reset_input_buffer()  # Limpiar buffer de entrada
                    self.serial_obj.reset_output_buffer()  # Limpiar buffer de salida
                    self.serial_obj.flush()  # Flush final

                    # 4. Pequeña pausa para estabilizar
                    time.sleep(0.2)

                    # 5. Cerrar puerto
                    self.serial_obj.close()
                    self.serial_obj = None
                except Exception as e:
                    # Si falla la limpieza, al menos cerrar el puerto
                    try:
                        self.serial_obj.close()
                    except:
                        pass
                    self.serial_obj = None

    def mark_failed(self):
        """Marca el puerto como fallido."""
        with self.lock:
            self.state = "failed"

    def get_elapsed_time(self) -> float:
        """Retorna minutos transcurridos desde switch_time."""
        with self.lock:
            if self.switch_time is None:
                return 0.0
            delta = datetime.now() - self.switch_time
            return delta.total_seconds() / 60.0

    def is_released(self) -> bool:
        """Verifica si el puerto ya fue liberado."""
        with self.lock:
            return self.state == "released"

    def set_changing_sim(self, changing: bool):
        """Marca el puerto como en proceso de cambio de SIM."""
        with self.lock:
            self.is_changing_sim = changing


class Orchestrator:
    """
    Orquestador principal del sistema mp_simclient.
    Gestiona el ciclo completo de rotación de SIMs.
    """

    def __init__(self, config_manager, logger):
        """
        Inicializa el orquestador.

        Args:
            config_manager: Instancia de ConfigManager
            logger: Logger configurado
        """
        self.config_manager = config_manager
        self.config = config_manager.config_data
        self.logger = logger

        # Componentes del sistema
        self.hardware = SimController(config_manager, logger)
        self.data_manager = DataManager(config_manager, logger)
        self.slot_manager = None  # Se inicializa después del escaneo
        self.ccid_analyzer = CCIDAnalyzer()  # Analizador de desajustes de CCID

        # Control de ejecución
        self.running = False
        self.simclient_process = None

        # Obtener configuración de tiempo
        self.cambio_fila_minutos = self.config.get("cambio_fila_minutos", 5)
        self.cambio_fila_segundos = self.cambio_fila_minutos * 60
        self.sim_intento_operativo = self.config.get("sim_intento_operativo", 3)
        self.max_workers = self.config.get("max_workers", 8)
        self.status_log_interval_minutes = self.config.get(
            "status_log_interval_minutes", 1
        )

        # Estados de puertos
        self.port_states = {}  # {port: PortState}

        # Control de logging periódico
        self.round_start_time = None
        self.round_end_time = None
        self.status_logging_active = False
        self.status_thread = None

        self.logger.info(f"Orquestador inicializado")
        self.logger.info(f"  - Ciclo ronda completa: {self.cambio_fila_minutos} min")
        self.logger.info(f"  - SIM intento operativo: {self.sim_intento_operativo} min")
        self.logger.info(f"  - Workers paralelos: {self.max_workers}")

    def _log_round_status(self):
        """
        Thread que genera logs periódicos con estadísticas de la ronda.
        Se ejecuta cada status_log_interval_minutes.
        """
        while self.status_logging_active:
            try:
                time.sleep(self.status_log_interval_minutes * 60)

                if not self.status_logging_active:
                    break

                # Timestamp actual
                now = datetime.now()
                current_time = now.strftime("%H:%M:%S")

                # Tiempo transcurrido y restante
                if self.round_start_time:
                    elapsed = (now - self.round_start_time).total_seconds() / 60
                else:
                    elapsed = 0

                if self.round_end_time:
                    remaining = (self.round_end_time - now).total_seconds() / 60
                else:
                    remaining = 0

                # Estadísticas de puertos
                total_ports = len(self.port_states)
                released_ports = sum(
                    1 for state in self.port_states.values() if state.is_released()
                )
                waiting_ports = sum(
                    1
                    for state in self.port_states.values()
                    if state.state == "waiting_registration"
                )
                failed_ports = sum(
                    1 for state in self.port_states.values() if state.state == "failed"
                )

                # Verificar si SimClient está corriendo
                simclient_status = "❌ NO CORRIENDO"
                try:
                    check = subprocess.run(
                        ["tasklist", "/FI", "IMAGENAME eq HeroSMS-Partners.exe"],
                        capture_output=True,
                        text=True,
                        timeout=2,
                    )
                    if "HeroSMS-Partners.exe" in check.stdout:
                        simclient_status = "✅ ACTIVO"
                except:
                    pass

                # Log estructurado con ADVERTENCIA si hay anomalías
                self.logger.info("═" * 70)
                if elapsed > (self.cambio_fila_minutos * 2):
                    self.logger.warning(f"⚠️  ESTADO DE RONDA ANORMAL [{current_time}]")
                else:
                    self.logger.info(f"📊 ESTADO DE RONDA [{current_time}]")
                self.logger.info("═" * 70)
                self.logger.info(f"⏱️  TIEMPOS:")
                self.logger.info(
                    f"   • Transcurrido: {elapsed:.1f} min / {self.cambio_fila_minutos} min"
                )
                self.logger.info(f"   • Restante: {remaining:.1f} min")

                # Mostrar progreso con advertencia si excede 100%
                progress_pct = (
                    (elapsed / self.cambio_fila_minutos * 100)
                    if self.cambio_fila_minutos > 0
                    else 0
                )
                if progress_pct > 150:
                    self.logger.warning(
                        f"   • Progreso: {progress_pct:.1f}% ⚠️  EXCEDIDO - POSIBLE THREAD BLOQUEADO"
                    )
                else:
                    self.logger.info(f"   • Progreso: {progress_pct:.1f}%")

                self.logger.info(f"📡 PUERTOS ({total_ports} total):")
                self.logger.info(f"   • ✅ Liberados (exitosos): {released_ports}")
                self.logger.info(f"   • ⏳ En monitoreo: {waiting_ports}")
                self.logger.info(f"   • ❌ Fallidos: {failed_ports}")
                self.logger.info(f"⚙️  CONFIGURACIÓN:")
                self.logger.info(
                    f"   • cambio_fila_minutos: {self.cambio_fila_minutos} min"
                )
                self.logger.info(
                    f"   • sim_intento_operativo: {self.sim_intento_operativo} min"
                )
                self.logger.info(f"   • max_workers: {self.max_workers}")
                self.logger.info(
                    f"   • status_log_interval: {self.status_log_interval_minutes} min"
                )
                self.logger.info(f"🖥️  SIMCLIENT: {simclient_status}")
                self.logger.info("═" * 70)

            except Exception as e:
                self.logger.error(f"Error en _log_round_status: {e}")

    def initialize_data(self, force_scan=False, generate_outputs=True):
        """
        Inicializa los datos del sistema.

        Args:
            force_scan: Si True, fuerza escaneo de hardware
            generate_outputs: Si True, genera archivos de salida (numero_simid, lista_pos)
        """
        self.logger.info("Inicializando datos del sistema...")

        # Obtener signal_data
        signal_data = self.data_manager.get_signal_data(
            force_new=force_scan, generate_outputs=generate_outputs
        )

        if not signal_data:
            self.logger.error("No hay datos de señal disponibles")
            return False

        # Inicializar SlotManager solo si no es modo solo-escaneo
        if generate_outputs:
            self.slot_manager = SlotManager(self.data_manager)

            status = self.slot_manager.get_status()
            self.logger.info(f"SlotManager inicializado:")
            self.logger.info(f"  - Puertos: {status['total_ports']}")
            self.logger.info(f"  - SIMs válidas: {status['total_valid_sims']}")

        return True

        return True

    def switch_all_modems_parallel(self):
        """
        Cambia todos los módems en paralelo (Arquitectura Barrier).

        Cada módem ejecuta: switch_sim -> reboot -> wait_for_signal
        Todos los hilos deben completar antes de continuar.

        Returns:
            True si todos los cambios fueron exitosos
        """
        self.logger.info("=" * 70)
        self.logger.info("INICIO DE CAMBIO PARALELO DE MÓDEMS")
        self.logger.info("=" * 70)

        threads = []
        results = {}

        # Obtener todos los puertos con slots válidos
        ports = self.slot_manager.get_all_ports()

        if not ports:
            self.logger.error("No hay puertos con slots válidos")
            return False

        self.logger.info(f"Preparando cambio en {len(ports)} módems...")

        # Preparar tareas de switch para ThreadPoolExecutor
        switch_tasks = []

        for port in ports:
            # Obtener siguiente slot para este puerto
            slot = self.slot_manager.get_next_slot(port)

            if not slot:
                self.logger.error(f"❌ ERROR: No hay slot disponible para {port}")
                continue

            # Obtener información del slot
            fila = int(slot.get("fila"))  # Convertir a entero
            col = slot.get("col")  # Ya es string formateado ('01', '02', etc.)
            numero = slot.get("numero", "N/A")
            ccid = slot.get("ccid", "N/A")

            # Encontrar el puerto de control (pool_com) para este modem
            pool_com = self._find_pool_for_port(port)

            if not pool_com:
                self.logger.critical(f"❌ CRITICO: No se encontró pool_com para {port}")
                continue

            self.logger.info(
                f"  📌 {port}: Fila {fila}, Col {col}, Phone {numero}, CCID {ccid}"
            )

            switch_tasks.append((port, pool_com, col, fila, results))

        # Ejecutar switches en paralelo con ThreadPoolExecutor
        self.logger.info(
            f"🚀 Lanzando {len(switch_tasks)} switches en paralelo (max_workers={self.max_workers})..."
        )
        start_time = time.time()

        with ThreadPoolExecutor(max_workers=self.max_workers) as executor:
            futures = [
                executor.submit(self._switch_single_modem, *task)
                for task in switch_tasks
            ]

            # BARRERA: Esperar a que TODOS terminen
            self.logger.info("⏳ Esperando a que todos los módems completen...")

            for future in futures:
                future.result()

        elapsed = time.time() - start_time
        self.logger.info(f"✅ Todos los módems completados en {elapsed:.1f}s")

        # Verificar resultados
        success_count = sum(1 for v in results.values() if v)
        total_count = len(results)

        self.logger.info(f"Resultado: {success_count}/{total_count} módems exitosos")
        self.logger.info("=" * 70)

        return success_count > 0

    def _switch_single_modem(self, port, pool_com, col, fila, results):
        """
        Cambia un único módem (ejecutado en hilo separado).

        Args:
            port: Puerto COM del módem (slot)
            pool_com: Puerto COM del SimBank (control)
            col: Columna de la SIM
            fila: Fila de la SIM
            results: Diccionario compartido para almacenar resultados
        """
        try:
            self.logger.info(f"[{port}] Iniciando cambio...")

            # PASO 1: Switch en SimBank
            switch_result = self.hardware.switch_sim(
                pool_com, col, fila, modem_port=port
            )

            if not switch_result["success"]:
                self.logger.error(f"[{port}] Fallo en switch_sim")
                results[port] = False
                return

            # Staggered Wait (Módulo 1)
            col_num = int(col)
            delay = (col_num - 1) * 3
            if delay > 0:
                self.logger.info(f"[{port}] Esperando {delay}s (staggered)")
                time.sleep(delay)

            # PASO 2: Abrir puerto y reiniciar módem
            import serial

            try:
                ser = serial.Serial(
                    port=port,
                    baudrate=self.config.get("baudrate", 115200),
                    timeout=self.config.get("at_timeout", 3),
                )

                # Detectar modelo
                model = self.hardware.detect_model(ser)
                self.logger.info(f"[{port}] Modelo: {model}")

                # Reiniciar módem
                reboot_ok = self.hardware.reboot_modem(ser, model)

                if not reboot_ok:
                    self.logger.warning(f"[{port}] Reinicio incompleto")

                # PASO 3: Esperar señal
                signal_ok, creg = self.hardware.wait_for_signal(ser, max_wait=60)

                if signal_ok:
                    self.logger.info(f"[{port}] ✅ Listo - CREG={creg}")
                    results[port] = True
                else:
                    self.logger.warning(f"[{port}] ⚠️  Sin señal - CREG={creg}")
                    results[port] = False

                ser.close()

            except serial.SerialException as e:
                self.logger.error(f"[{port}] Error serial: {e}")
                results[port] = False

        except Exception as e:
            self.logger.error(f"[{port}] Error inesperado: {e}")
            results[port] = False

    def _find_pool_for_port(self, port):
        """
        Encuentra el puerto de control (pool_com) para un puerto de módem.

        Args:
            port: Puerto COM del módem

        Returns:
            Puerto COM del SimBank o None
        """
        for bank in self.config.get("simbanks", []):
            for modem in bank.get("modems", []):
                if modem.get("port") == port:
                    return bank.get("control_port")
        return None

    def _initialize_all_pools(self):
        """
        Inicializa todos los SimBanks (UNA VEZ por pool_com).

        NO se llama por cada slot, solo una vez por cada pool_com único.
        Ejemplo: Si tenemos COM19 y COM20, se inicializan solo 2 veces.

        Returns:
            True si al menos un pool se inicializó correctamente
        """
        # Obtener lista única de pool_coms
        pool_coms = set()
        for bank in self.config.get("simbanks", []):
            control_port = bank.get("control_port")
            if control_port:
                pool_coms.add(control_port)

        if not pool_coms:
            self.logger.error("❌ No se encontraron puertos de control (pool_com)")
            return False

        self.logger.info(
            f"Inicializando {len(pool_coms)} SimBanks: {', '.join(sorted(pool_coms))}"
        )

        success_count = 0
        for pool_com in sorted(pool_coms):
            if self.hardware.initialize_simbank(pool_com):
                success_count += 1

        self.logger.info(
            f"✅ Inicialización completada: {success_count}/{len(pool_coms)} SimBanks OK"
        )

        # Considerar exitoso si al menos uno funciona
        return success_count > 0

    def launch_simclient(self):
        """
        Lanza el proceso SimClient usando la ruta del config.

        Protocolo Módulo 3, PASO 3: Launch en modo Sniffer.
        """
        # Obtener ruta expandida desde config
        simclient_path = self.config_manager.get_path("simclient_exec_path")

        if not simclient_path:
            self.logger.error("simclient_exec_path no configurado en config.json")
            return False

        if not os.path.exists(simclient_path):
            self.logger.warning(f"SimClient no encontrado en: {simclient_path}")
            self.logger.info("Continuando sin SimClient (modo testing)")
            return False

        try:
            start_time = datetime.now().strftime("%H:%M:%S.%f")[:-3]
            self.logger.info(f"🚀 [{start_time}] Lanzando SimClient: {simclient_path}")

            # Obtener directorio de SimClient para establecer como cwd
            simclient_dir = os.path.dirname(simclient_path)

            # Lanzar proceso en segundo plano con su propio directorio de trabajo
            self.simclient_process = subprocess.Popen(
                [simclient_path],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                cwd=simclient_dir,  # SimClient se ejecuta en su propia carpeta
            )

            success_time = datetime.now().strftime("%H:%M:%S.%f")[:-3]
            self.logger.info(
                f"  ✅ [{success_time}] SimClient iniciado (PID: {self.simclient_process.pid})"
            )
            self.logger.info(f"  📁 Directorio de trabajo: {simclient_dir}")
            return True

        except Exception as e:
            self.logger.error(f"Error al lanzar SimClient: {e}")
            return False

    def open_all_serials(self) -> Dict[str, Any]:
        """
        Abre seriales de todos los puertos para bloquearlos.
        Incluye puertos con lista_pos Y puertos vacíos (sin registro).
        Esto impide que SimClient los tome mientras hacemos el switch.

        Implementa retry con delay para esperar liberación de puertos.

        Returns:
            Diccionario {port: serial_object}
        """
        import serial

        self.logger.info("🔒 Abriendo seriales de todos los puertos...")
        serial_objects = {}

        # Puertos con lista_pos
        ports = self.slot_manager.get_all_ports()

        # Puertos vacíos (sin lista_pos pero con SIMs no registradas)
        empty_ports = self.slot_manager.get_empty_ports()

        # Combinar ambos tipos de puertos
        all_ports = list(set(ports + empty_ports))

        self.logger.info(f"  📋 {len(ports)} puertos con lista_pos")
        if empty_ports:
            self.logger.info(
                f"  🔍 {len(empty_ports)} puertos vacíos (mantenidos por programa): {', '.join(empty_ports)}"
            )

        max_retries = 3
        retry_delay = 2  # segundos

        for port in all_ports:
            success = False
            last_error = None

            for attempt in range(1, max_retries + 1):
                try:
                    ser = serial.Serial(
                        port=port,
                        baudrate=self.config.get("baudrate", 115200),
                        timeout=3,
                    )
                    serial_objects[port] = ser

                    # Indicar si es puerto vacío
                    if port in empty_ports:
                        self.logger.info(
                            f"  🔒 {port}: Serial abierto (puerto vacío - NO para SimClient)"
                        )
                    else:
                        self.logger.info(f"  ✅ {port}: Serial abierto (bloqueado)")

                    success = True
                    break
                except Exception as e:
                    last_error = e
                    if attempt < max_retries:
                        self.logger.warning(
                            f"  ⚠️  {port}: Intento {attempt}/{max_retries} falló, reintentando en {retry_delay}s..."
                        )
                        time.sleep(retry_delay)

            if not success:
                self.logger.error(
                    f"  ❌ {port}: Error después de {max_retries} intentos: {last_error}"
                )

        return serial_objects

    def switch_reboot_and_release_parallel(self, serial_objects: Dict[str, Any]):
        """
        Proceso paralelo: Switch + Reboot + Wait + Liberar.

        Cada puerto ejecuta en su propio hilo:
        1. Switch según lista_pos.json
        2. Reboot según modelo
        3. Wait for signal
        4. Si registrado → liberar a SimClient
        5. Si no → mantener en monitoreo

        Args:
            serial_objects: Diccionario de objetos serial abiertos
        """
        self.logger.info("=" * 70)
        self.logger.info("🚀 INICIO DE PROCESO PARALELO: SWITCH + REBOOT + WAIT")
        self.logger.info("=" * 70)

        process_tasks = []
        empty_port_tasks = []  # Tareas para puertos sin lista_pos
        results = {}

        # Puertos con lista_pos válida
        ports = self.slot_manager.get_all_ports()

        # Puertos sin lista_pos (sin SIMs registradas)
        empty_ports = self.slot_manager.get_empty_ports()

        self.port_states.clear()

        self.logger.info(f"Preparando proceso en {len(ports)} puertos con lista_pos...")
        if empty_ports:
            self.logger.info(
                f"  ⚠️  {len(empty_ports)} puertos sin lista_pos (buscarán SIMs no registradas)"
            )

        # Crear hilo por cada puerto con lista_pos
        for port in ports:
            # ROTACIÓN: Obtener SIGUIENTE slot (avanza índice automáticamente)
            slot = self.slot_manager.get_next_slot(port)

            if not slot:
                self.logger.error(f"❌ ERROR: {port}: No hay slot disponible")
                continue

            fila = int(slot.get("fila"))
            col = slot.get("col")
            numero = slot.get("numero", "N/A")
            ccid = slot.get("ccid", "N/A")

            # Encontrar pool_com
            pool_com = self._find_pool_for_port(port)

            if not pool_com:
                self.logger.critical(f"❌ CRITICO: {port}: No se encontró pool_com")
                continue

            # Crear estado del puerto
            state = PortState(port)
            state.start_monitoring(slot)
            state.serial_obj = serial_objects.get(port)  # Asignar serial abierto
            self.port_states[port] = state

            self.logger.info(
                f"  📌 {port}: Fila {fila}, Col {col}, Phone {numero}, CCID {ccid}"
            )

            # Agregar tarea
            process_tasks.append((port, pool_com, col, fila, slot, state, results))

        # Preparar tareas para puertos vacíos (buscar SIMs no registradas)
        for port in empty_ports:
            # Obtener filas con número pero sin registro
            unregistered_slots = self.slot_manager.get_unregistered_slots_for_port(port)

            if not unregistered_slots:
                self.logger.warning(
                    f"⚠️  {port}: Sin lista_pos Y sin SIMs no registradas - OMITIENDO"
                )
                continue

            # Encontrar pool_com
            pool_com = self._find_pool_for_port(port)

            if not pool_com:
                self.logger.critical(f"❌ CRITICO: {port}: No se encontró pool_com")
                continue

            # Crear estado del puerto
            state = PortState(port)
            state.serial_obj = serial_objects.get(port)
            self.port_states[port] = state

            self.logger.info(
                f"  🔍 {port}: {len(unregistered_slots)} SIMs no registradas disponibles"
            )

            # Agregar tarea especial para slots vacíos
            empty_port_tasks.append(
                (port, pool_com, unregistered_slots, state, results)
            )

        # Ejecutar todas las tareas en paralelo con ThreadPoolExecutor
        total_tasks = len(process_tasks) + len(empty_port_tasks)
        self.logger.info(
            f"🚀 Lanzando {total_tasks} procesos en paralelo ({len(process_tasks)} normales + {len(empty_port_tasks)} vacíos)"
        )
        start_time = time.time()

        # Timestamp global de fin de ronda (todos los threads deben terminar antes)
        self.round_start_time = datetime.now()
        round_end_time = self.round_start_time + timedelta(
            minutes=self.cambio_fila_minutos
        )
        self.round_end_time = round_end_time
        self.logger.info(
            f"⏰ Tiempo límite de ronda: {round_end_time.strftime('%H:%M:%S')} ({self.cambio_fila_minutos}min)"
        )

        # Iniciar thread de logging periódico
        self.status_logging_active = True
        self.status_thread = threading.Thread(
            target=self._log_round_status, daemon=True
        )
        self.status_thread.start()
        self.logger.info(
            f"📊 Logging de estado activado (cada {self.status_log_interval_minutes} min)"
        )

        # Timeout: cambio_fila_minutos + 30s de margen
        max_thread_wait = (self.cambio_fila_minutos * 60) + 30

        with ThreadPoolExecutor(max_workers=self.max_workers) as executor:
            # Lanzar tareas normales (con round_end_time)
            futures = [
                executor.submit(self._process_single_port, *task, round_end_time)
                for task in process_tasks
            ]

            # Lanzar tareas para puertos vacíos (con round_end_time)
            futures.extend(
                [
                    executor.submit(self._process_empty_port, *task, round_end_time)
                    for task in empty_port_tasks
                ]
            )

            # Esperar a que todos terminen (en paralelo, no secuencial)
            self.logger.info("⏳ Esperando a que todos los puertos completen...")

            for future in as_completed(futures, timeout=max_thread_wait):
                try:
                    future.result()  # Capturar excepciones
                except Exception as e:
                    self.logger.warning(f"⚠️ Task generó excepción: {e}")

        elapsed = time.time() - start_time
        self.logger.info(f"✅ Fase paralela completada en {elapsed:.1f}s")

        # Detener logging periódico
        self.status_logging_active = False
        if self.status_thread:
            self.status_thread.join(timeout=2)

        # Verificar si ya se alcanzó el tiempo límite de la ronda
        time_until_round_end = (round_end_time - datetime.now()).total_seconds()

        if time_until_round_end <= 0:
            # Ya se alcanzó el límite de tiempo, terminar inmediatamente
            self.logger.info(
                f"⏰ Tiempo de ronda alcanzado ({self.cambio_fila_minutos}min) - Finalizando ciclo"
            )
        else:
            # Aún hay tiempo, continuar con retry si hay puertos fallidos
            self.logger.info(
                f"⏳ Tiempo restante en ronda: {time_until_round_end:.1f}s"
            )

            # Identificar puertos sin registro
            failed_ports = [port for port, success in results.items() if not success]

            if failed_ports:
                self.logger.info(
                    f"⚠️  {len(failed_ports)} puertos sin registro: {', '.join(failed_ports)}"
                )
                self.logger.info(f"🔄 Continuando intentos con siguientes SIMs...")
                # Reintentar con puertos fallidos durante el tiempo restante
                self._retry_failed_ports(
                    failed_ports,
                    serial_objects,
                    time_until_round_end,
                    results,
                    round_end_time,
                )
            else:
                # Todos se registraron, esperar hasta completar la ronda
                self.logger.info(
                    f"✅ Todos los puertos registrados, esperando fin de ronda..."
                )
                time.sleep(time_until_round_end)

        # Resumen
        success_count = sum(1 for v in results.values() if v)
        total_count = len(results)

        self.logger.info(f"Resultado: {success_count}/{total_count} puertos exitosos")
        self.logger.info("=" * 70)

        return success_count > 0

    def _process_single_port(
        self,
        port: str,
        pool_com: str,
        col: str,
        fila: int,
        slot: dict,
        state: PortState,
        results: dict,
        round_end_time: datetime,
    ):
        """
        Thread individual: switch → reboot → monitoreo continuo (cada 15s).
        Cada thread se auto-gestiona y libera su puerto cuando se registra.

        Args:
            port: Puerto COM del módem
            pool_com: Puerto COM del SimBank
            col: Columna
            fila: Fila
            slot: Datos completos del slot (incluye model)
            state: Estado del puerto
            results: Diccionario compartido de resultados
            round_end_time: Timestamp límite global de la ronda
        """
        try:
            start_time = datetime.now()
            self.logger.info(
                f"[{start_time.strftime('%H:%M:%S.%f')[:-3]}] [{port}] Iniciando proceso..."
            )

            # PASO 1: Switch en SimBank (con retry automático)
            expected_ccid = slot.get("ccid", "N/A")

            # Ejecutar switch (devuelve dict con detalles)
            switch_start = datetime.now()
            switch_result = self.hardware.switch_sim(
                pool_com, col, fila, modem_port=port
            )
            switch_duration = (datetime.now() - switch_start).total_seconds()

            if not switch_result["success"]:
                self.logger.error(
                    f"[{datetime.now().strftime('%H:%M:%S.%f')[:-3]}] [{port}] ❌ Fallo en comando AT+SWIT ({switch_duration:.2f}s)"
                )
                self.logger.error(f"[{port}]    Comando: {switch_result['command']}")
                self.logger.error(f"[{port}]    Respuesta: {switch_result['response']}")
                self.logger.error(f"[{port}]    Intentos: {switch_result['attempts']}")
                results[port] = False
                return

            self.logger.info(
                f"[{datetime.now().strftime('%H:%M:%S.%f')[:-3]}] [{port}] ✅ AT+SWIT OK ({switch_duration:.2f}s, intento {switch_result['attempts']})"
            )

            # Esperar a que el SimBank complete el cambio físico (aumentado a 8s)
            self.logger.info(
                f"[{datetime.now().strftime('%H:%M:%S.%f')[:-3]}] [{port}] ⏳ Esperando cambio físico (8s)..."
            )
            time.sleep(8)

            # PASO 2 y 3: Reboot + Verificación CCID con RETRY COMPLETO si falla
            max_switch_retries = 3  # Intentos totales de switch+reboot+verificación
            ccid_verified = False

            for switch_attempt in range(max_switch_retries):
                if switch_attempt > 0:
                    self.logger.warning(
                        f"[{port}] 🔄 REINTENTO #{switch_attempt + 1} de switch completo (cambio físico falló)"
                    )

                    # Reintentar el switch desde cero
                    switch_start = datetime.now()
                    switch_result = self.hardware.switch_sim(
                        pool_com, col, fila, modem_port=port
                    )
                    switch_duration = (datetime.now() - switch_start).total_seconds()

                    if not switch_result["success"]:
                        self.logger.error(f"[{port}] ❌ Reintento de switch falló")
                        self.logger.error(
                            f"[{port}]    Comando: {switch_result['command']}"
                        )
                        self.logger.error(
                            f"[{port}]    Respuesta: {switch_result['response']}"
                        )
                        if switch_attempt == max_switch_retries - 1:
                            results[port] = False
                            return
                        continue

                    self.logger.info(
                        f"[{port}] ✅ Reintento de switch OK (intento {switch_result['attempts']})"
                    )
                    time.sleep(8)  # Esperar cambio físico nuevamente

                # PASO 2: Reboot MANDATORIO del módem (slot_com)
                model = slot.get("model", "EC25")
                if not (state.serial_obj and state.serial_obj.is_open):
                    self.logger.error(
                        f"[{datetime.now().strftime('%H:%M:%S.%f')[:-3]}] [{port}] Serial no disponible para reboot"
                    )
                    results[port] = False
                    return

                reboot_start = datetime.now()
                self.logger.info(
                    f"[{reboot_start.strftime('%H:%M:%S.%f')[:-3]}] [{port}] 🔄 Reiniciando módem (modelo: {model})..."
                )
                success = self.hardware.reboot_modem(state.serial_obj, model)
                reboot_duration = (datetime.now() - reboot_start).total_seconds()

                if not success:
                    self.logger.warning(
                        f"[{datetime.now().strftime('%H:%M:%S.%f')[:-3]}] [{port}] ⚠️  Reboot completado con advertencias ({reboot_duration:.2f}s)"
                    )
                else:
                    self.logger.info(
                        f"[{datetime.now().strftime('%H:%M:%S.%f')[:-3]}] [{port}] ✅ Reboot OK ({reboot_duration:.2f}s)"
                    )

                # Esperar estabilización del módem después del reboot
                self.logger.info(
                    f"[{datetime.now().strftime('%H:%M:%S.%f')[:-3]}] [{port}] ⏳ Esperando estabilización (15s)..."
                )
                time.sleep(15)

                # Staggered wait (para evitar picos de carga)
                col_num = int(col)
                delay = (col_num - 1) * 3
                if delay > 0:
                    self.logger.info(f"[{port}] Esperando {delay}s (staggered)")
                    time.sleep(delay)

                # PASO 3: Verificación CCID post-reboot
                ccid_check_retries = 3
                ccid_start = datetime.now()
                self.logger.info(
                    f"[{ccid_start.strftime('%H:%M:%S.%f')[:-3]}] [{port}] 🔍 Verificando CCID (intento switch {switch_attempt + 1}/{max_switch_retries})..."
                )

                for attempt in range(ccid_check_retries):
                    # Verificar CCID
                    identity = self.hardware.verify_sim_identity(state.serial_obj)

                    if identity["success"] and identity["ccid"]:
                        actual_ccid = identity["ccid"]

                        if actual_ccid == expected_ccid:
                            # ✅ CCID correcto
                            self.logger.info(
                                f"[{port}] ✅ CCID verificado correctamente"
                            )
                            ccid_verified = True
                            break
                        else:
                            # ❌ CCID incorrecto
                            self.logger.warning(
                                f"[{port}] ⚠️  CCID incorrecto (esperado: {expected_ccid}, real: {actual_ccid})"
                            )

                            if attempt < ccid_check_retries - 1:
                                self.logger.info(
                                    f"[{port}] 🔄 Esperando {attempt + 1}/{ccid_check_retries}..."
                                )
                                time.sleep(3)
                                continue
                            else:
                                # CCID no coincide después de verificaciones
                                analysis = self.ccid_analyzer.analyze_mismatch(
                                    port=port,
                                    expected_fila=slot.get("fila"),
                                    expected_col=slot.get("col"),
                                    expected_ccid=expected_ccid,
                                    actual_ccid=actual_ccid,
                                )

                                self.logger.error(
                                    f"[{port}] ❌ CCID no coincide - Switch físico falló"
                                )
                                self.logger.error(f"[{port}] 🔍 Detalles del AT+SWIT:")
                                self.logger.error(
                                    f"[{port}]    Comando: {switch_result['command']}"
                                )
                                self.logger.error(
                                    f"[{port}]    Respuesta: {switch_result['response']}"
                                )
                                self.logger.error(
                                    f"[{port}]    Intentos exitosos: {switch_result['attempts']}"
                                )
                                diagnosis_lines = self.ccid_analyzer.format_diagnosis(
                                    analysis
                                )
                                for line in diagnosis_lines:
                                    self.logger.error(f"[{port}] {line}")

                                # Si no es el último intento de switch, romper para reintentar switch
                                if switch_attempt < max_switch_retries - 1:
                                    break
                    else:
                        # No se pudo leer CCID
                        self.logger.warning(
                            f"[{port}] ⚠️  No se pudo leer CCID (intento {attempt + 1})"
                        )

                        if attempt < ccid_check_retries - 1:
                            time.sleep(3)
                            continue

                # Si se verificó, salir del loop de switch retries
                if ccid_verified:
                    break

            if not ccid_verified:
                self.logger.error(
                    f"[{datetime.now().strftime('%H:%M:%S.%f')[:-3]}] [{port}] ❌ Verificación CCID falló"
                )
                results[port] = False
                return

            ccid_duration = (datetime.now() - ccid_start).total_seconds()
            self.logger.info(
                f"[{datetime.now().strftime('%H:%M:%S.%f')[:-3]}] [{port}] ✅ CCID verificado ({ccid_duration:.2f}s)"
            )

            # PASO 4: MONITOREO CONTINUO (cada 15s durante cambio_fila_minutos)
            monitor_start = datetime.now()
            self.logger.info(
                f"[{monitor_start.strftime('%H:%M:%S.%f')[:-3]}] [{port}] 🔍 Iniciando monitoreo continuo (máx {self.cambio_fila_minutos}min)"
            )

            check_interval = 15  # segundos
            max_duration = timedelta(minutes=self.cambio_fila_minutos)
            reboot_threshold = self.sim_intento_operativo / 3.0
            change_threshold = self.sim_intento_operativo
            reboot_done = False
            sim_changed = False
            check_count = 0
            consecutive_errors = 0  # Contador de errores consecutivos
            max_consecutive_errors = 10  # Máximo de errores antes de abandonar

            while self.running:
                # VERIFICACIÓN GLOBAL AL INICIO: Si se alcanzó el límite, salir INMEDIATAMENTE
                if datetime.now() >= round_end_time:
                    self.logger.warning(
                        f"[{port}] ⏰ Límite de ronda alcanzado ({self.cambio_fila_minutos}min) - Terminando thread"
                    )
                    results[port] = False
                    return

                elapsed_time = (datetime.now() - monitor_start).total_seconds() / 60.0

                # Verificar si completó el tiempo máximo local (redundante pero mantener por seguridad)
                if datetime.now() - monitor_start >= max_duration:
                    self.logger.info(
                        f"[{port}] ⏰ Tiempo máximo alcanzado ({self.cambio_fila_minutos}min) sin registro"
                    )
                    results[port] = False
                    return

                check_count += 1

                # Actualizar timestamp del último monitoreo
                state.last_monitor_time = datetime.now()

                # VERIFICAR CREG (usando el serial ya abierto)
                creg = self.hardware.check_creg_with_serial(state.serial_obj)
                sim_phone = (
                    state.current_sim.get("numero", "N/A")
                    if state.current_sim
                    else "N/A"
                )
                sim_ccid = (
                    state.current_sim.get("ccid", "N/A") if state.current_sim else "N/A"
                )

                # Verificar si hay error de comunicación
                if creg == "ERROR":
                    consecutive_errors += 1
                    self.logger.warning(
                        f"[{port}] ⚠️  Error leyendo CREG (consecutivos: {consecutive_errors}/{max_consecutive_errors})"
                    )

                    if consecutive_errors >= max_consecutive_errors:
                        self.logger.error(
                            f"[{port}] ❌ Demasiados errores consecutivos ({consecutive_errors}) - Abandonando puerto"
                        )
                        results[port] = False
                        return

                    # Esperar antes del siguiente check
                    time.sleep(check_interval)
                    continue
                else:
                    # Reset contador si obtuvimos respuesta válida
                    consecutive_errors = 0

                # SI SE REGISTRÓ → LIBERAR Y TERMINAR THREAD
                if creg in ["1", "5"]:
                    network_type = "Home" if creg == "1" else "Roaming"
                    self.logger.info(
                        f"[{port}] ✅ Registrado ({network_type}) en {elapsed_time:.1f}min"
                    )
                    self.liberar_puerto(port)
                    results[port] = True
                    return  # Thread termina aquí exitosamente

                # Log de verificación
                if check_count == 1 or check_count % 4 == 0:  # Log cada minuto aprox
                    if creg in ["0", "2", "3"]:
                        self.logger.warning(
                            f"[{port}] ⚠️  Ciclo {check_count}: CREG={creg} (sin registro), Phone={sim_phone}, CCID={sim_ccid}, Tiempo={elapsed_time:.1f}min"
                        )
                    else:
                        self.logger.warning(
                            f"[{port}] ⚠️  Ciclo {check_count}: CREG={creg}, Phone={sim_phone}, CCID={sim_ccid}, Tiempo={elapsed_time:.1f}min"
                        )

                # Reboot global a sim_intento_operativo/3
                if elapsed_time >= reboot_threshold and not reboot_done:
                    self.logger.info(
                        f"[{port}] 🔄 Reboot adicional ({reboot_threshold:.1f}min)"
                    )
                    self.hardware.reboot_modem(state.serial_obj, model)
                    self.logger.info(
                        f"[{port}] ⏳ Esperando estabilización del módem (15s)..."
                    )
                    time.sleep(15)
                    reboot_done = True

                # Cambio de SIM a sim_intento_operativo
                if elapsed_time >= change_threshold and not sim_changed:
                    self.logger.warning(
                        f"[{port}] ⏰ {elapsed_time:.1f}min sin registro, cambiando SIM..."
                    )
                    self._cambiar_sim_sincronico(port, state)
                    sim_changed = True

                # Esperar antes del siguiente check
                time.sleep(check_interval)

            # Si llegamos aquí (self.running=False), el sistema se está deteniendo
            self.logger.info(f"[{port}] Sistema deteniéndose, finalizando thread")
            results[port] = False

        except Exception as e:
            total_duration = (datetime.now() - start_time).total_seconds()
            self.logger.error(
                f"[{datetime.now().strftime('%H:%M:%S.%f')[:-3]}] [{port}] Error en thread: {e} (duración total: {total_duration:.1f}s)"
            )
            results[port] = False
        finally:
            # CRÍTICO: Solo cerrar serial si se registró (True) o si el sistema se está deteniendo
            # NO cerrar si quedó sin registro (False) porque entrará a reintentos
            total_duration = (datetime.now() - start_time).total_seconds()

            # Solo cerrar si se liberó exitosamente
            if results.get(port) == True:
                if state.serial_obj and state.serial_obj.is_open:
                    try:
                        state.serial_obj.close()
                        self.logger.debug(
                            f"[{datetime.now().strftime('%H:%M:%S.%f')[:-3]}] [{port}] Serial cerrado tras registro exitoso (duración: {total_duration:.1f}s)"
                        )
                    except Exception as e:
                        self.logger.warning(
                            f"[{datetime.now().strftime('%H:%M:%S.%f')[:-3]}] [{port}] Error al cerrar serial: {e}"
                        )
            else:
                # Puerto sin registro - mantener serial abierto para reintentos
                self.logger.debug(
                    f"[{datetime.now().strftime('%H:%M:%S.%f')[:-3]}] [{port}] Serial mantenido abierto para reintentos (duración: {total_duration:.1f}s)"
                )

    def _process_empty_port(
        self,
        port: str,
        pool_com: str,
        unregistered_slots: List[Dict],
        state: PortState,
        results: dict,
        round_end_time: datetime,
    ):
        """
        Thread para puerto vacío: intenta registro alternando entre SIMs no registradas.
        Estos puertos NO se liberan a SimClient, se mantienen todo el ciclo buscando registro.

        Args:
            port: Puerto COM del módem
            pool_com: Puerto COM del SimBank
            unregistered_slots: Lista de slots con número pero sin registro
            state: Estado del puerto
            results: Diccionario compartido de resultados
            round_end_time: Timestamp límite global de la ronda
        """
        try:
            start_time = datetime.now()
            self.logger.info(
                f"[{start_time.strftime('%H:%M:%S.%f')[:-3]}] [{port}] 🔍 Iniciando búsqueda activa ({len(unregistered_slots)} SIMs)..."
            )

            # Inicializar índice de rotación
            rotation_index = 0
            sim_attempt_time = self.sim_intento_operativo * 60  # 3 minutos por SIM
            reboot_threshold_time = (
                sim_attempt_time / 3.0
            )  # 1 minuto para reboot adicional

            last_change_time = time.time()
            reboot_done = False

            # Ciclo continuo hasta que se registre o termine el thread
            while self.running:
                # Seleccionar SIM actual con rotación
                current_slot = unregistered_slots[
                    rotation_index % len(unregistered_slots)
                ]
                fila = int(current_slot.get("fila"))
                col = current_slot.get("col")
                numero = current_slot.get("numero", "N/A")
                ccid = current_slot.get("ccid", "N/A")

                # Calcular tiempo desde último cambio
                time_since_change = time.time() - last_change_time

                # Cambiar a siguiente SIM si pasó sim_intento_operativo
                if time_since_change >= sim_attempt_time:
                    self.logger.info(
                        f"[{port}] ⏱️  {sim_attempt_time / 60:.0f} min sin registro - cambiando a siguiente SIM"
                    )
                    rotation_index += 1
                    last_change_time = time.time()
                    reboot_done = False
                    continue

                # Reboot adicional a 1 minuto si no se ha hecho
                if time_since_change >= reboot_threshold_time and not reboot_done:
                    self.logger.info(
                        f"[{port}] 🔄 Reboot adicional tras {reboot_threshold_time / 60:.0f} min"
                    )
                    try:
                        if state.serial_obj and state.serial_obj.is_open:
                            model = "EC25"  # Asumir EC25 por defecto
                            self.hardware.reboot_modem(state.serial_obj, model)
                            reboot_done = True
                    except Exception as e:
                        self.logger.warning(
                            f"[{port}] ⚠️  Error en reboot adicional: {e}"
                        )

                # Primera verificación o después de cambio - hacer switch
                if time_since_change < 1:
                    self.logger.info(
                        f"[{port}] 🔄 Probando Fila {fila}, Col {col}, Phone {numero}"
                    )

                    # PASO 1: Switch
                    try:
                        switch_result = self.hardware.switch_sim(
                            pool_com, col, fila, modem_port=port
                        )
                        if not switch_result["success"]:
                            self.logger.warning(
                                f"[{port}] ⚠️  Switch falló, reintentando..."
                            )
                            time.sleep(5)
                            continue

                        # Esperar cambio físico
                        time.sleep(5)
                    except Exception as e:
                        self.logger.warning(f"[{port}] ⚠️  Error en switch: {e}")
                        time.sleep(5)
                        continue

                    # PASO 2: Reboot
                    try:
                        if not state.serial_obj or not state.serial_obj.is_open:
                            state.serial_obj = serial.Serial(port, 115200, timeout=3)

                        model = "EC25"  # Asumir EC25 por defecto
                        self.hardware.reboot_modem(state.serial_obj, model)
                    except Exception as e:
                        self.logger.warning(f"[{port}] ⚠️  Error en reboot: {e}")

                    # PASO 3: Esperar estabilización + registro
                    stabilization = self.config.get("reboot_stabilization_seconds", 15)
                    network_wait = self.config.get(
                        "network_registration_first_seconds", 20
                    )
                    total_wait = stabilization + network_wait

                    self.logger.info(
                        f"[{port}] ⏳ Esperando estabilización + registro ({total_wait}s)..."
                    )
                    time.sleep(total_wait)

                # VERIFICACIÓN ADICIONAL antes de chequear CREG
                if datetime.now() >= round_end_time:
                    self.logger.warning(
                        f"[{port}] ⏰ Límite de ronda alcanzado durante monitoreo - Terminando"
                    )
                    results[port] = False
                    return

                # PASO 4: Verificar CREG cada 15s (continuo durante sim_intento_operativo)
                try:
                    if not state.serial_obj or not state.serial_obj.is_open:
                        state.serial_obj = serial.Serial(port, 115200, timeout=3)

                    state.serial_obj.write(b"AT+CREG?\r\n")
                    time.sleep(0.8)
                    response = state.serial_obj.read(200).decode(
                        "utf-8", errors="ignore"
                    )

                    # Extraer CREG
                    creg = "0"
                    for line in response.split("\n"):
                        if "+CREG:" in line:
                            parts = line.split(",")
                            if len(parts) >= 2:
                                creg = parts[1].strip()
                                break

                    # Log del estado cada verificación
                    self.logger.debug(
                        f"[{port}] 📶 CREG={creg} (tiempo: {time_since_change:.0f}s/{sim_attempt_time:.0f}s)"
                    )

                    if creg in ["1", "5"]:
                        elapsed = (datetime.now() - start_time).total_seconds()
                        self.logger.info(
                            f"[{port}] ✅ ¡PRIMER REGISTRO ENCONTRADO! CREG={creg}, Fila {fila}, Phone {numero}"
                        )
                        self.logger.info(
                            f"[{port}] 🗺️  Iniciando mapeo completo de todas las SIMs no registradas..."
                        )

                        # MAPEO COMPLETO: Probar todas las SIMs no registradas
                        registered_slots = self._complete_mapping_for_empty_port(
                            port, pool_com, unregistered_slots, state
                        )

                        if registered_slots:
                            self.logger.info(
                                f"[{port}] 🎓 Mapeo completo: {len(registered_slots)}/{len(unregistered_slots)} SIMs se registraron"
                            )

                            # GRADUAR a producción
                            self.slot_manager.add_port_to_production(
                                port, registered_slots
                            )

                            # Ahora SÍ liberar a SimClient
                            self.logger.info(
                                f"[{port}] 🚀 Puerto graduado, liberando a SimClient..."
                            )
                            results[port] = True  # True = liberar

                            # Cerrar serial para que SimClient lo tome
                            if state.serial_obj and state.serial_obj.is_open:
                                state.serial_obj.close()
                                self.logger.info(
                                    f"[{port}] ✅ Serial cerrado, disponible para SimClient"
                                )
                        else:
                            self.logger.warning(
                                f"[{port}] ⚠️  Mapeo completo falló, no se encontraron SIMs registradas"
                            )
                            results[port] = False

                        return

                    # VERIFICACIÓN ADICIONAL antes de sleep
                    if datetime.now() >= round_end_time:
                        self.logger.warning(
                            f"[{port}] ⏰ Límite de ronda alcanzado - Terminando empty_port"
                        )
                        results[port] = False
                        return

                    # Esperar 15s antes de siguiente verificación
                    time.sleep(15)

                except Exception as e:
                    self.logger.warning(f"[{port}] ⚠️  Error verificando CREG: {e}")
                    time.sleep(5)

        except Exception as e:
            self.logger.error(f"[{port}] ❌ Error crítico en proceso empty_port: {e}")
            results[port] = False

        finally:
            # NO cerrar serial - mantener ocupado
            self.logger.debug(
                f"[{port}] 🔒 Thread empty_port terminado, serial mantenido abierto"
            )

    def _complete_mapping_for_empty_port(
        self, port: str, pool_com: str, unregistered_slots: List[Dict], state: PortState
    ) -> List[Dict]:
        """
        Mapea TODAS las SIMs no registradas para determinar cuáles SÍ se registran.
        Retorna lista de slots que lograron registro.

        Args:
            port: Puerto COM del módem
            pool_com: Puerto COM del SimBank
            unregistered_slots: Lista completa de slots a probar
            state: Estado del puerto

        Returns:
            Lista de slots que se registraron (CREG=1 o 5)
        """
        registered_slots = []
        total = len(unregistered_slots)

        self.logger.info(f"[{port}] 🗺️  Mapeando {total} SIMs no registradas...")

        for idx, slot in enumerate(unregistered_slots, 1):
            fila = int(slot.get("fila"))
            col = slot.get("col")
            numero = slot.get("numero", "N/A")
            ccid = slot.get("ccid", "N/A")

            self.logger.info(
                f"[{port}] [{idx}/{total}] Probando Fila {fila}, Col {col}, Phone {numero}"
            )

            try:
                # PASO 1: Switch
                switch_result = self.hardware.switch_sim(
                    pool_com, col, fila, modem_port=port
                )
                if not switch_result["success"]:
                    self.logger.warning(f"[{port}] [{idx}/{total}] ⚠️  Switch falló")
                    continue

                # Esperar cambio físico
                time.sleep(5)

                # PASO 2: Reboot
                if not state.serial_obj or not state.serial_obj.is_open:
                    state.serial_obj = serial.Serial(port, 115200, timeout=3)

                model = "EC25"  # Asumir EC25
                self.hardware.reboot_modem(state.serial_obj, model)

                # PASO 3: Esperar estabilización + registro
                stabilization = self.config.get("reboot_stabilization_seconds", 15)
                network_wait = self.config.get("network_registration_first_seconds", 20)
                total_wait = stabilization + network_wait

                self.logger.info(
                    f"[{port}] [{idx}/{total}] ⏳ Esperando {total_wait}s..."
                )
                time.sleep(total_wait)

                # PASO 4: Verificar CREG
                if not state.serial_obj or not state.serial_obj.is_open:
                    state.serial_obj = serial.Serial(port, 115200, timeout=3)

                state.serial_obj.write(b"AT+CREG?\r\n")
                time.sleep(0.8)
                response = state.serial_obj.read(200).decode("utf-8", errors="ignore")

                # Extraer CREG
                creg = "0"
                for line in response.split("\n"):
                    if "+CREG:" in line:
                        parts = line.split(",")
                        if len(parts) >= 2:
                            creg = parts[1].strip()
                            break

                if creg in ["1", "5"]:
                    self.logger.info(
                        f"[{port}] [{idx}/{total}] ✅ REGISTRADA - CREG={creg}"
                    )
                    registered_slots.append(slot)
                else:
                    self.logger.info(
                        f"[{port}] [{idx}/{total}] ❌ No registrada - CREG={creg}"
                    )

            except Exception as e:
                self.logger.warning(f"[{port}] [{idx}/{total}] ⚠️  Error: {e}")

        self.logger.info(
            f"[{port}] 🗺️  Mapeo completado: {len(registered_slots)}/{total} registradas"
        )
        return registered_slots

    def _retry_failed_ports(
        self,
        failed_ports: List[str],
        serial_objects: Dict,
        remaining_time: float,
        results: dict,
        round_end_time: datetime,
    ):
        """
        Reintenta con siguientes SIMs en puertos que no lograron registro.
        Cada puerto ejecuta en su propio thread EN PARALELO.
        Se ejecuta durante el tiempo restante del ciclo.
        Cada SIM tiene sim_intento_operativo minutos para registrarse.

        Args:
            failed_ports: Lista de puertos sin registro
            serial_objects: Diccionario de seriales abiertos
            remaining_time: Tiempo restante en segundos
            results: Diccionario de resultados por puerto
            round_end_time: Timestamp límite global de la ronda
        """
        if not failed_ports:
            return

        # Validar tiempo restante - asegurar mínimo razonable
        if remaining_time <= 0:
            self.logger.warning(
                f"⚠️  Sin tiempo restante para reintentos (remaining={remaining_time:.1f}s)"
            )
            return

        # Establecer timeout mínimo de 30s para evitar TimeoutError prematuro
        actual_timeout = max(remaining_time + 10, 30)

        self.logger.info(
            f"🔄 Lanzando reintentos en paralelo para {len(failed_ports)} puertos..."
        )
        self.logger.info(
            f"   Tiempo restante: {remaining_time:.1f}s, Timeout: {actual_timeout:.1f}s"
        )

        # Preparar tareas de retry paralelas
        retry_tasks = []
        for port in failed_ports:
            state = self.port_states.get(port)
            if not state:
                self.logger.warning(f"[{port}] ⚠️  Sin estado, omitiendo reintentos")
                continue

            retry_tasks.append((port, state, remaining_time, results, round_end_time))

        # Ejecutar reintentos en paralelo
        try:
            with ThreadPoolExecutor(max_workers=self.max_workers) as executor:
                futures = [
                    executor.submit(self._retry_single_port, *task)
                    for task in retry_tasks
                ]

                # Esperar a que todos terminen o se acabe el tiempo
                for future in as_completed(futures, timeout=actual_timeout):
                    try:
                        future.result()
                    except Exception as e:
                        self.logger.warning(f"⚠️  Error en thread de retry: {e}")
        except TimeoutError as e:
            # Algunos threads no terminaron a tiempo - esto es esperado cuando se acaba el tiempo de ronda
            unfinished = sum(1 for f in futures if not f.done())
            self.logger.warning(
                f"⚠️  Timeout en reintentos: {unfinished} threads no terminaron en {actual_timeout:.1f}s"
            )
            self.logger.info(
                f"   Los threads restantes terminarán naturalmente al alcanzar round_end_time"
            )
        except Exception as e:
            self.logger.error(f"❌ Error en _retry_failed_ports: {e}")

    def _retry_single_port(
        self,
        port: str,
        state: PortState,
        remaining_time: float,
        results: dict,
        round_end_time: datetime,
    ):
        """
        Reintenta registro para un puerto específico en su propio thread.
        Alterna entre SIMs cada sim_intento_operativo minutos.

        Args:
            port: Puerto COM
            state: Estado del puerto
            remaining_time: Tiempo máximo de reintentos
            results: Diccionario compartido de resultados
            round_end_time: Timestamp límite global de la ronda
        """
        retry_start = time.time()
        check_interval = 15  # Verificar cada 15s
        sim_attempt_time = self.sim_intento_operativo * 60  # Tiempo por SIM en segundos
        reboot_threshold_time = sim_attempt_time / 3.0  # Reboot a 1/3 del tiempo
        network_reg_wait = self.config.get("network_registration_first_seconds", 20)
        reboot_stabilization = self.config.get("reboot_stabilization_seconds", 15)

        # Verificar serial (debería estar abierto desde thread original)
        if state.serial_obj and state.serial_obj.is_open:
            self.logger.debug(f"[{port}] ✅ Serial abierto para reintentos")
        else:
            self.logger.warning(f"[{port}] ⚠️  Serial cerrado, reabriendo...")
            try:
                if state.serial_obj:
                    try:
                        state.serial_obj.close()
                    except:
                        pass
                state.serial_obj = serial.Serial(port, 115200, timeout=3)
                self.logger.info(f"[{port}] 🔌 Serial reabierto")
            except Exception as e:
                self.logger.error(f"[{port}] ❌ No se pudo reabrir serial: {e}")
                return

        # Variables de control
        last_change_time = None
        reboot_done = False

        # Ciclo de reintentos hasta que se registre o se acabe el tiempo
        while self.running:
            # VERIFICACIÓN GLOBAL: Respetar el límite de tiempo de la ronda
            if datetime.now() >= round_end_time:
                self.logger.warning(
                    f"[{port}] ⏰ Límite de ronda alcanzado - Terminando retry thread"
                )
                return

            retry_elapsed = time.time() - retry_start

            # Verificar si se acabó el tiempo local (redundante pero mantener)
            if retry_elapsed >= remaining_time:
                self.logger.info(f"[{port}] ⏰ Tiempo de reintentos completado")
                break

            # Determinar si necesita cambiar SIM
            needs_change = False
            if last_change_time is None:
                # Primera vez, cambiar inmediatamente
                needs_change = True
            else:
                # Verificar si pasó sim_intento_operativo
                time_since_change = time.time() - last_change_time
                if time_since_change >= sim_attempt_time:
                    self.logger.warning(
                        f"[{port}] ⏰ {time_since_change / 60:.1f}min sin registro, cambiando SIM..."
                    )
                    needs_change = True

            if needs_change:
                # VERIFICACIÓN ADICIONAL antes de cambiar SIM
                if datetime.now() >= round_end_time:
                    self.logger.warning(
                        f"[{port}] ⏰ Límite de ronda alcanzado - Terminando retry antes de cambio"
                    )
                    return

                # Cambiar a siguiente SIM
                change_start = time.time()
                success = self._cambiar_sim_sincronico(port, state)
                if not success:
                    self.logger.warning(
                        f"[{port}] ⚠️  No se pudo cambiar SIM, reintentando..."
                    )
                    time.sleep(5)
                    continue

                last_change_time = change_start
                reboot_done = False

                # Esperar estabilización + registro
                self.logger.info(
                    f"[{port}] ⏳ Esperando estabilización ({reboot_stabilization}s)..."
                )
                time.sleep(reboot_stabilization)

                self.logger.info(
                    f"[{port}] 📡 Esperando registro de red ({network_reg_wait}s)..."
                )
                time.sleep(network_reg_wait)

                # Verificar registro
                try:
                    creg = self.hardware.check_creg_with_serial(state.serial_obj)

                    if creg in ["1", "5"]:
                        network_type = "Home" if creg == "1" else "Roaming"
                        elapsed_minutes = (time.time() - change_start) / 60
                        self.logger.info(
                            f"[{port}] ✅ Registrado ({network_type}) en {elapsed_minutes:.1f}min"
                        )
                        self.liberar_puerto(port)
                        results[port] = True
                        return  # Terminado con éxito
                    else:
                        self.logger.warning(
                            f"[{port}] ⚠️  CREG={creg} después de cambio"
                        )
                except Exception as e:
                    self.logger.error(f"[{port}] ❌ Error verificando CREG: {e}")
            else:
                # Ya cambió recientemente, verificar si necesita reboot o solo check
                time_since_change = time.time() - last_change_time

                # REBOOT ADICIONAL a sim_intento_operativo/3 (1 minuto)
                if time_since_change >= reboot_threshold_time and not reboot_done:
                    self.logger.info(
                        f"[{port}] 🔄 Reboot adicional ({reboot_threshold_time / 60:.1f}min sin registro)"
                    )

                    # Obtener modelo
                    current_sim = state.current_sim
                    model = current_sim.get("model", "EC25") if current_sim else "EC25"

                    try:
                        success = self.hardware.reboot_modem(state.serial_obj, model)
                        if success:
                            self.logger.info(
                                f"[{port}] ⏳ Esperando estabilización ({reboot_stabilization}s)..."
                            )
                            time.sleep(reboot_stabilization)
                            reboot_done = True
                        else:
                            self.logger.warning(
                                f"[{port}] ⚠️  Fallo en reboot adicional"
                            )
                    except Exception as e:
                        self.logger.error(f"[{port}] ❌ Error en reboot adicional: {e}")

                    # VERIFICACIÓN ADICIONAL después de reboot
                    if datetime.now() >= round_end_time:
                        self.logger.warning(
                            f"[{port}] ⏰ Límite de ronda alcanzado - Terminando retry"
                        )
                        return

                    # Verificar CREG después del reboot
                    try:
                        creg = self.hardware.check_creg_with_serial(state.serial_obj)
                        if creg in ["1", "5"]:
                            network_type = "Home" if creg == "1" else "Roaming"
                            self.logger.info(
                                f"[{port}] ✅ Registrado ({network_type}) tras reboot adicional"
                            )
                            self.liberar_puerto(port)
                            results[port] = True
                            return  # Terminado con éxito
                        else:
                            self.logger.info(
                                f"[{port}] 🔍 CREG={creg} después de reboot adicional"
                            )
                    except Exception as e:
                        self.logger.error(f"[{port}] ❌ Error verificando CREG: {e}")
                else:
                    # Solo verificar registro cada 15s
                    try:
                        creg = self.hardware.check_creg_with_serial(state.serial_obj)

                        if creg in ["1", "5"]:
                            network_type = "Home" if creg == "1" else "Roaming"
                            self.logger.info(
                                f"[{port}] ✅ Registrado ({network_type}) tras {time_since_change / 60:.1f}min"
                            )
                            self.liberar_puerto(port)
                            results[port] = True
                            return  # Terminado con éxito
                        else:
                            self.logger.debug(
                                f"[{port}] 📶 CREG={creg}, esperando... ({time_since_change / 60:.1f}min)"
                            )
                    except Exception as e:
                        self.logger.error(f"[{port}] ❌ Error verificando CREG: {e}")

            # VERIFICACIÓN ADICIONAL antes de sleep
            if datetime.now() >= round_end_time:
                self.logger.warning(
                    f"[{port}] ⏰ Límite de ronda alcanzado - Terminando retry"
                )
                return

            # Esperar antes del siguiente check
            time.sleep(check_interval)

        # Si llegamos aquí, no se registró en el tiempo disponible
        self.logger.info(f"[{port}] ⏰ Reintentos finalizados sin registro")
        if state.serial_obj and state.serial_obj.is_open:
            try:
                state.serial_obj.close()
                self.logger.info(f"[{port}] 🔌 Serial cerrado")
            except Exception as e:
                self.logger.warning(f"[{port}] ⚠️  Error cerrando serial: {e}")

    def liberar_puerto(self, port: str):
        """
        Libera un puerto para que SimClient lo tome.
        Espera al menos 5 segundos desde el último monitoreo antes de liberar.
        Cierra el serial de Python.

        Args:
            port: Puerto COM a liberar
        """
        state = self.port_states.get(port)
        if not state:
            return

        try:
            # Esperar al menos 5 segundos desde el último monitoreo
            if state.last_monitor_time:
                elapsed_since_monitor = (
                    datetime.now() - state.last_monitor_time
                ).total_seconds()
                if elapsed_since_monitor < 5.0:
                    wait_time = 5.0 - elapsed_since_monitor
                    self.logger.info(
                        f"⏳ {port}: Esperando {wait_time:.1f}s antes de liberar (5s desde último monitoreo)"
                    )
                    time.sleep(wait_time)

            state.mark_released()
            sim_numero = (
                state.current_sim.get("numero", "N/A") if state.current_sim else "N/A"
            )
            sim_ccid = (
                state.current_sim.get("ccid", "N/A") if state.current_sim else "N/A"
            )
            self.logger.info(
                f"🔓 {port}: Liberado a SimClient - Phone: {sim_numero}, CCID: {sim_ccid}"
            )
        except Exception as e:
            self.logger.error(f"Error al liberar {port}: {e}")

    def _cambiar_sim_sincronico(self, port: str, state: PortState):
        """
        Cambia SIM de forma SINCRÓNICA (sin lanzar thread hijo).
        Se ejecuta dentro del thread de monitoreo del puerto.

        Args:
            port: Puerto COM a cambiar
            state: Estado del puerto
        """
        try:
            # LOG: Número y CCID anterior
            old_numero = (
                state.current_sim.get("numero", "N/A") if state.current_sim else "N/A"
            )
            old_ccid = (
                state.current_sim.get("ccid", "N/A") if state.current_sim else "N/A"
            )
            old_fila = (
                state.current_sim.get("fila", "N/A") if state.current_sim else "N/A"
            )

            # Obtener siguiente slot
            slot = self.slot_manager.get_next_slot(port)

            if not slot:
                self.logger.error(f"❌ ERROR: [{port}] No hay más slots disponibles")
                state.mark_failed()
                return False

            fila = int(slot.get("fila"))
            col = slot.get("col")
            numero = slot.get("numero", "N/A")
            ccid = slot.get("ccid", "N/A")
            model = slot.get("model", "EC25")

            # LOG DETALLADO: Transición completa
            self.logger.info(f"[{port}] 🔄 CAMBIO DE SIM")
            self.logger.info(
                f"[{port}]    Anterior: Fila {old_fila}, Phone {old_numero}, CCID {old_ccid}"
            )
            self.logger.info(
                f"[{port}]    Nueva:    Fila {fila}, Col {col}, Phone {numero}, CCID {ccid}"
            )

            # Encontrar pool_com
            pool_com = self._find_pool_for_port(port)
            if not pool_com:
                self.logger.critical(f"❌ CRITICO: [{port}] No se encontró pool_com")
                return False

            # Realizar switch
            switch_result = self.hardware.switch_sim(
                pool_com, col, fila, modem_port=port
            )

            if not switch_result["success"]:
                self.logger.error(f"[{port}] Fallo en switch_sim")
                return False

            # Esperar staggered
            col_num = int(col)
            delay = (col_num - 1) * 3
            if delay > 0:
                time.sleep(delay)

            # Reboot del módem (usando el serial que ya tenemos abierto)
            if state.serial_obj and state.serial_obj.is_open:
                success = self.hardware.reboot_modem(state.serial_obj, model)
                if not success:
                    self.logger.warning(f"[{port}] Fallo en reboot")
                    return False
            else:
                self.logger.error(f"[{port}] Serial no disponible para reboot")
                return False

            # Actualizar estado
            state.start_monitoring(slot)

            # LOG: Confirmar actualización
            new_numero = (
                state.current_sim.get("numero", "N/A") if state.current_sim else "N/A"
            )
            new_ccid = (
                state.current_sim.get("ccid", "N/A") if state.current_sim else "N/A"
            )
            self.logger.info(
                f"[{port}] ✅ Cambio completado - Phone: {new_numero}, CCID: {new_ccid}"
            )

            return True

        except Exception as e:
            self.logger.error(f"[{port}] Error al cambiar SIM: {e}")
            return False

    def _cambiar_al_siguiente_simcard_thread(self, port: str):
        """
        Worker thread para cambiar SIM sin bloquear el monitoreo.

        IMPORTANTE: NO cierra SimClient. El serial permanece abierto
        en manos de Python durante todo el monitoreo.

        Args:
            port: Puerto COM a cambiar
        """
        state = self.port_states.get(port)
        if not state:
            return

        state.set_changing_sim(True)

        try:
            # LOG: Número y CCID anterior
            old_numero = (
                state.current_sim.get("numero", "N/A") if state.current_sim else "N/A"
            )
            old_ccid = (
                state.current_sim.get("ccid", "N/A") if state.current_sim else "N/A"
            )
            old_fila = (
                state.current_sim.get("fila", "N/A") if state.current_sim else "N/A"
            )

            # Obtener siguiente slot
            slot = self.slot_manager.get_next_slot(port)

            if not slot:
                self.logger.error(f"❌ ERROR: {port}: No hay más slots disponibles")
                state.mark_failed()
                return

            fila = int(slot.get("fila"))
            col = slot.get("col")
            numero = slot.get("numero", "N/A")
            ccid = slot.get("ccid", "N/A")
            model = slot.get("model", "EC25")

            # LOG DETALLADO: Transición completa
            self.logger.info(f"🔄 {port}: CAMBIO DE SIM")
            self.logger.info(
                f"   Anterior: Fila {old_fila}, Phone {old_numero}, CCID {old_ccid}"
            )
            self.logger.info(
                f"   Nueva:    Fila {fila}, Col {col}, Phone {numero}, CCID {ccid}"
            )

            # Encontrar pool_com
            pool_com = self._find_pool_for_port(port)
            if not pool_com:
                self.logger.critical(f"❌ CRITICO: {port}: No se encontró pool_com")
                return

            # Realizar switch
            switch_result = self.hardware.switch_sim(
                pool_com, col, fila, modem_port=port
            )

            if not switch_result["success"]:
                self.logger.error(f"{port}: Fallo en switch_sim")
                return False

            # Esperar staggered
            col_num = int(col)
            delay = (col_num - 1) * 3
            if delay > 0:
                time.sleep(delay)

            # Reboot del módem (usando el serial que ya tenemos abierto)
            if state.serial_obj and state.serial_obj.is_open:
                success = self.hardware.reboot_modem(state.serial_obj, model)
                if not success:
                    self.logger.warning(f"{port}: Fallo en reboot")
            else:
                self.logger.error(f"{port}: Serial no disponible para reboot")
                return False

            # Actualizar estado
            state.start_monitoring(slot)

            # LOG: Confirmar actualización
            new_numero = (
                state.current_sim.get("numero", "N/A") if state.current_sim else "N/A"
            )
            new_ccid = (
                state.current_sim.get("ccid", "N/A") if state.current_sim else "N/A"
            )
            self.logger.info(
                f"  ✅ {port}: Cambio completado - Phone: {new_numero}, CCID: {new_ccid}"
            )

        except Exception as e:
            self.logger.error(f"Error al cambiar {port}: {e}")
        finally:
            state.set_changing_sim(False)

    def _reboot_port_thread(self, port: str, state: "PortState", model: str):
        """Worker thread para reboot global sin bloquear monitoreo."""
        try:
            self.logger.info(f"  🔄 {port}: Reboot global...")
            success = self.hardware.reboot_modem(state.serial_obj, model)
            if success:
                self.logger.info(f"    ✅ {port}: Reboot completado")
        except Exception as e:
            self.logger.error(f"  ❌ {port}: Error en reboot global - {e}")

    def run_production_cycle(self):
        """
        Ejecuta una ronda completa de producción.

        Secuencia reorganizada:
        0. Inicializar SimBanks (UNA VEZ por pool_com)
        1. Kill SimClient y verificar cierre
        2. Abrir seriales de todos los puertos (bloquearlos)
        3. Launch SimClient en modo sniffer
        4. Proceso paralelo por puerto (cada thread se auto-gestiona):
           a. Switch según lista_pos.json
           b. Reboot según modelo
           c. Monitoreo continuo cada 15s durante cambio_fila_minutos
           d. Si registrado → liberar inmediatamente (SimClient lo toma)
           e. Si pasa sim_intento_operativo → cambiar SIM y continuar
           f. Thread termina al completar cambio_fila_minutos o registrarse
        """
        self.logger.info("=" * 70)
        self.logger.info("🔄 INICIO DE RONDA DE PRODUCCIÓN")
        self.logger.info("=" * 70)

        # PASO 0: Kill SimClient primero (liberar puertos pool_com)
        close_time = datetime.now().strftime("%H:%M:%S")
        self.logger.info("=" * 70)
        self.logger.info(f"🔴 PASO 0 [{close_time}]: CERRANDO SIMCLIENT")
        self.logger.info("=" * 70)
        kill_ok = self.hardware.kill_simclient()

        if not kill_ok:
            self.logger.error("⚠️  SimClient no se cerró correctamente")
            self.logger.info("Esperando 5 segundos adicionales...")
            time.sleep(5)
        else:
            verify_time = datetime.now().strftime("%H:%M:%S")
            self.logger.info(f"✅ [{verify_time}] SimClient cerrado y verificado")
            time.sleep(2)

        # PASO 1: Inicializar SimBanks (ahora pool_com están disponibles)
        self.logger.info("PASO 1: Inicializando SimBanks...")
        if not self._initialize_all_pools():
            self.logger.error("⚠️  Fallo en inicialización de SimBanks, continuando...")

        # PASO 2: Abrir seriales (bloquear puertos)
        self.logger.info("PASO 2: Bloqueando puertos con seriales...")
        serial_objects = self.open_all_serials()

        if not serial_objects:
            self.logger.error("No se pudieron abrir seriales")
            return False

        # PASO 3: Launch SimClient
        launch_time = datetime.now().strftime("%H:%M:%S")
        self.logger.info("=" * 70)
        self.logger.info(f"🟢 PASO 3 [{launch_time}]: LANZANDO SIMCLIENT")
        self.logger.info("=" * 70)
        launch_ok = self.launch_simclient()

        if not launch_ok:
            self.logger.warning(
                "⚠️  SimClient no se lanzó, continuando de todas formas..."
            )
        else:
            success_time = datetime.now().strftime("%H:%M:%S")
            self.logger.info(f"✅ [{success_time}] SimClient lanzado correctamente")
            time.sleep(3)

        # PASO 4: Proceso paralelo (switch + reboot + monitoreo continuo por puerto)
        # Cada thread maneja su propio monitoreo y se libera cuando se registra
        self.logger.info(
            "PASO 4: Proceso paralelo de puertos (con monitoreo integrado)..."
        )
        self.switch_reboot_and_release_parallel(serial_objects)

        self.logger.info("✅ Ronda completada - Todos los threads finalizaron")
        self.logger.info(f"🔄 Próxima ronda iniciará con nuevos slots (rotación)")
        return True

    def _get_next_change_time(self):
        """Calcula y retorna la hora del próximo cambio."""
        next_time = datetime.now() + timedelta(minutes=self.cambio_fila_minutos)
        return next_time.strftime("%H:%M:%S")

    def run_continuous(self):
        """
        Ejecuta el sistema en modo continuo 24/7.
        Cada cambio_fila_minutos ejecuta una ronda completa.
        """
        self.running = True
        cycle_count = 0

        self.logger.info("🚀 INICIANDO MODO PRODUCCIÓN CONTINUO")
        self.logger.info(f"   Rondas cada {self.cambio_fila_minutos} minutos")
        self.logger.info("   Presiona Ctrl+C para detener")
        self.logger.info("=" * 70)

        try:
            while self.running:
                cycle_count += 1
                self.logger.info(f"\n📊 RONDA #{cycle_count}")

                success = self.run_production_cycle()

                if not success:
                    self.logger.error(
                        "Ronda falló, esperando 5 minutos antes de reintentar..."
                    )
                    time.sleep(300)

        except KeyboardInterrupt:
            self.logger.info("\n⚠️  Ctrl+C detectado, deteniendo...")
        finally:
            self.shutdown()

    def shutdown(self):
        """Apagado graceful del sistema."""
        self.logger.info("=" * 70)
        self.logger.info("🛑 APAGANDO SISTEMA")
        self.logger.info("=" * 70)

        self.running = False

        # Terminar SimClient si está corriendo
        self.hardware.kill_simclient()

        self.logger.info("✅ Sistema detenido correctamente")


def show_menu():
    """Muestra el menú interactivo."""
    print("\n" + "=" * 70)
    print("  MP_SIMCLIENT - SISTEMA DE GESTIÓN SIM-FARMING")
    print("=" * 70)
    print("\nOPCIONES:")
    print("  1. Iniciar modo producción (continuo)")
    print("  2. Ejecutar un solo ciclo (testing)")
    print("  3. Escanear hardware y generar signal_data.json")
    print("  4. Ver estado actual (slot_state.json)")
    print("  5. Salir")
    print("\n" + "=" * 70)

    while True:
        try:
            choice = input("\nSelecciona una opción (1-5): ").strip()
            if choice in ["1", "2", "3", "4", "5"]:
                return choice
            print("⚠️  Opción inválida, intenta nuevamente")
        except (KeyboardInterrupt, EOFError):
            return "5"


def main():
    """Función principal."""
    print_startup_banner()

    # Parsear argumentos
    parser = argparse.ArgumentParser(description="MP_SIMCLIENT - Sistema SIM-Farming")
    parser.add_argument(
        "--new",
        action="store_true",
        help="Iniciar con escaneo completo del hardware + archivos de salida",
    )
    parser.add_argument(
        "--scan-only",
        action="store_true",
        help="Solo escanear hardware (signal_data.csv), sin generar archivos de salida",
    )
    parser.add_argument(
        "--resume", action="store_true", help="Reanudar desde estado guardado"
    )
    parser.add_argument(
        "--cycle", action="store_true", help="Ejecutar un solo ciclo (testing)"
    )
    parser.add_argument(
        "-v",
        "--verbose",
        action="count",
        default=0,
        help="Aumentar verbosidad (-v: INFO, -vv: DEBUG, -vvv: DETALLADO)",
    )

    args = parser.parse_args()

    # Configurar logger con nivel de verbosidad
    logger = setup_logger(verbose_level=args.verbose)
    log_system_info(logger)

    # Cargar configuración
    try:
        config_manager = ConfigManager()
        log_config_summary(logger, config_manager.config_data)
    except Exception as e:
        logger.error(f"Error al cargar configuración: {e}")
        return 1

    # Crear orquestador
    orchestrator = Orchestrator(config_manager, logger)

    # Configurar handler para Ctrl+C
    def signal_handler(sig, frame):
        logger.info("\n⚠️  Señal de interrupción recibida")
        orchestrator.shutdown()
        sys.exit(0)

    signal.signal(signal.SIGINT, signal_handler)

    # Determinar modo de operación
    if args.new:
        # Modo: Escaneo completo + archivos de salida
        logger.info("Modo: --new (escaneo completo + archivos de salida)")
        if not orchestrator.initialize_data(force_scan=True, generate_outputs=True):
            logger.error("Error en inicialización de datos")
            return 1
        orchestrator.run_continuous()

    elif args.scan_only:
        # Modo: Solo escaneo, sin archivos de salida
        logger.info("Modo: --scan-only (solo signal_data.csv)")
        if not orchestrator.initialize_data(force_scan=True, generate_outputs=False):
            logger.error("Error en escaneo de hardware")
            return 1
        logger.info("✅ Escaneo completado. signal_data.csv generado.")
        logger.info("   Para generar archivos de salida, ejecuta sin argumentos.")
        return 0

    elif args.resume:
        # Modo: Reanudar desde estado guardado
        logger.info("Modo: --resume (estado guardado)")
        if not orchestrator.initialize_data(force_scan=False, generate_outputs=True):
            logger.error("Error en inicialización de datos")
            return 1
        orchestrator.run_continuous()

    elif args.cycle:
        # Modo: Un solo ciclo (testing)
        logger.info("Modo: --cycle (ciclo único)")
        if not orchestrator.initialize_data(force_scan=False, generate_outputs=True):
            logger.error("Error en inicialización de datos")
            return 1
        orchestrator.run_production_cycle()

    else:
        # Modo por defecto: Regenerar archivos de salida desde signal_data.csv existente
        if os.path.exists(os.path.join(os.getcwd(), "data", "signal_data.csv")):
            logger.info("Modo: Regenerar archivos de salida desde signal_data.csv")
            if not orchestrator.initialize_data(
                force_scan=False, generate_outputs=True
            ):
                logger.error("Error al generar archivos de salida")
                return 1
            logger.info("✅ Archivos de salida regenerados correctamente")
            return 0
        else:
            # Si no existe signal_data.csv, mostrar menú interactivo
            while True:
                choice = show_menu()

                if choice == "1":
                    # Producción continua
                    if not orchestrator.initialize_data(
                        force_scan=False, generate_outputs=True
                    ):
                        logger.error("Error en inicialización de datos")
                        continue
                    orchestrator.run_continuous()
                    break

                elif choice == "2":
                    # Un solo ciclo
                    if not orchestrator.initialize_data(
                        force_scan=False, generate_outputs=True
                    ):
                        logger.error("Error en inicialización de datos")
                        continue
                    orchestrator.run_production_cycle()

                elif choice == "3":
                    # Escanear hardware
                    logger.info("Iniciando escaneo de hardware...")
                    orchestrator.initialize_data(force_scan=True, generate_outputs=True)
                    print("\n✅ Escaneo completado. Revisa signal_data.csv")

                elif choice == "4":
                    # Ver estado
                    if orchestrator.slot_manager is None:
                        orchestrator.initialize_data(
                            force_scan=False, generate_outputs=True
                        )

                    status = orchestrator.slot_manager.get_status()
                    print("\n" + "=" * 70)
                    print("ESTADO ACTUAL DEL SISTEMA")
                    print("=" * 70)
                    print(f"Total puertos: {status['total_ports']}")
                    print(f"Total SIMs válidas: {status['total_valid_sims']}")
                    print(f"Archivo de estado: {status['state_file']}")
                    print(f"Estado existe: {status['state_exists']}")
                    print("\nPUERTOS:")
                    for port, info in status["ports"].items():
                        print(
                            f"  {port}: {info['valid_sims']} SIMs, índice actual: {info['current_index']}"
                        )
                    print("=" * 70)

                elif choice == "5":
                    # Salir
                    logger.info("Saliendo del programa")
                    break

    return 0


if __name__ == "__main__":
    sys.exit(main())
