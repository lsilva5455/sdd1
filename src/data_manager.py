"""
DataManager - Gestión de datos del hardware real mediante escaneo AT.
Módulo de producción sin mocks.
"""
import csv
import json
import os
import re
import time
import serial
import threading
import logging
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple


class DataManager:
    """Gestiona la recolección y persistencia de datos desde hardware real."""
    
    def __init__(self, config_manager, logger=None):
        self.config = config_manager.config_data
        self.config_manager = config_manager
        self.signal_data = []
        self.lock = threading.Lock()
        self.logger = logger or logging.getLogger(__name__)
        
        # Crear directorio data/ si no existe
        self.data_dir = os.path.join(os.getcwd(), 'data')
        os.makedirs(self.data_dir, exist_ok=True)
        
    def get_signal_data(self, force_new: bool = False, generate_outputs: bool = True) -> List[Dict]:
        """
        Obtiene los datos de señal. Si force_new=True, escanea el hardware.
        
        Args:
            force_new: Si True, ejecuta escaneo físico completo
            generate_outputs: Si True, genera archivos de salida (numero_simid, lista_pos)
            
        Returns:
            Lista de diccionarios con datos de cada SIM
        """
        signal_data_file = os.path.join(self.data_dir, 'signal_data.csv')
        
        if force_new or not os.path.exists(signal_data_file):
            self.logger.info("\n🔍 Generando datos desde hardware real...")
            
            # IMPORTANTE: Eliminar slot_state.json para reiniciar índices a cero
            slot_state_file = os.path.join(self.data_dir, 'slot_state.json')
            if os.path.exists(slot_state_file):
                os.remove(slot_state_file)
                self.logger.info("🔄 slot_state.json eliminado - índices se reiniciarán a 0")
            
            self.signal_data = self._scan_real_hardware(self.config, signal_data_file)
            
            self.logger.info(f"✅ Generación completada: {signal_data_file}")
            
            # Generar archivos de salida solo si está habilitado
            if generate_outputs:
                self._generate_output_files()
                
                # Duplicar archivos si está configurado
                self._mirror_data_files()
        else:
            # Cargar desde archivo existente
            self.signal_data = self._load_signal_data_csv(signal_data_file)
            
            # Si se solicita, regenerar archivos de salida desde CSV existente
            if generate_outputs:
                self.logger.info("\n📄 Regenerando archivos de salida desde signal_data.csv existente...")
                self._generate_output_files()
                self._mirror_data_files()
                
        return self.signal_data
    
    def _scan_real_hardware(self, config: Dict, output_file: str) -> List[Dict]:
        """
        Escanea el hardware físico real usando AT+SWIT y comandos AT.
        Paralelización por FILA: Todas las columnas de una fila se procesan en paralelo.
        Guardado PROGRESIVO: Cada fila se guarda inmediatamente en CSV.
        
        Args:
            config: Configuración del sistema
            output_file: Ruta del CSV donde guardar progresivamente
        
        Returns:
            Lista con datos recolectados de cada SIM
        """
        self.logger.info("⚙️  Iniciando escaneo físico para generar Verdad del Hardware...")
        self.logger.info(f"📁 Guardado progresivo en: {output_file}")
        
        filas = config.get('filas', 16)
        baudrate = config.get('baudrate', 115200)
        timeout = config.get('at_timeout', 3)
        sdata_iteraciones = config.get('sdata_iteraciones', 3)
        sdata_intervalo = config.get('sdata_intervalo_iteracion_segundos', 5)
        switch_wait = config.get('switch_wait_seconds', 3.2)
        reboot_stabilization = config.get('reboot_stabilization_seconds', 15)
        network_reg_first = config.get('network_registration_first_seconds', 20)
        network_reg_retry = config.get('network_registration_retry_seconds', 5)
        max_workers = config.get('max_workers', 8)
        
        self.logger.info(f"📊 Configuración de escaneo:")
        self.logger.info(f"   - Iteraciones por slot: {sdata_iteraciones}")
        self.logger.info(f"   - Intervalo entre iteraciones: {sdata_intervalo}s")
        self.logger.info(f"   - Espera post-switch: {switch_wait}s")
        self.logger.info(f"   - Estabilización post-reboot: {reboot_stabilization}s")
        self.logger.info(f"   - Registro red (1ra vez): {network_reg_first}s")
        self.logger.info(f"   - Registro red (reintentos): {network_reg_retry}s")
        self.logger.info(f"   - Workers paralelos: {max_workers}")
        
        # Inicializar timer de escaneo
        scan_start_time = datetime.now()
        
        results = []
        results_lock = threading.Lock()  # Proteger lista compartida
        simbank_locks = {}
        
        # Diccionario para acumular slots que necesitan monitoreo
        # Estructura: {slot_com: [{pool_com, fila, col, ccid, numero}, ...]}
        monitoring_queue = {}
        monitoring_rotation = {}  # Índice de rotación para cada slot_port
        monitoring_lock = threading.Lock()
        
        # Crear locks por cada SimBank
        for bank in config.get('simbanks', []):
            control_port = bank['control_port']
            simbank_locks[control_port] = threading.Lock()
        
        # Iterar por todas las filas (secuencial)
        for fila in range(1, filas + 1):
            fila_start_time = datetime.now()
            self.logger.info(f"\n📊 Escaneando FILA {fila:02d}/{filas} (paralelo por columnas)...")
            
            # Preparar tareas para ThreadPoolExecutor
            scan_tasks = []
            
            for bank_idx, bank in enumerate(config.get('simbanks', []), 1):
                control_port = bank['control_port']
                modems = bank.get('modems', [])
                
                for modem in modems:
                    slot_port = modem['port']
                    col = modem['col']
                    
                    self.logger.info(f"  🔌 Pool {bank_idx} | Slot {col} ({slot_port}) -> Fila {fila:04d}")
                    
                    # Agregar tarea a la lista
                    scan_tasks.append((
                        control_port, col, fila, slot_port,
                        baudrate, timeout, sdata_iteraciones, sdata_intervalo, switch_wait,
                        reboot_stabilization, network_reg_first, network_reg_retry,
                        simbank_locks[control_port], results, results_lock,
                        monitoring_queue, monitoring_lock
                    ))
            
            # Ejecutar todas las tareas en paralelo con ThreadPoolExecutor
            with ThreadPoolExecutor(max_workers=max_workers) as executor:
                futures = []
                for task_args in scan_tasks:
                    future = executor.submit(self._scan_single_slot, *task_args)
                    futures.append(future)
                
                # BARRIER: Esperar a que TODAS las tareas de esta fila terminen
                for future in futures:
                    future.result()  # Bloquea hasta completar
            
            # VERIFICACIÓN: Comparar CCID en signal_data vs CCID real
            self.logger.info(f"🔍 Verificando consistencia de FILA {fila:02d}...")
            verification_passed = self._verify_fila_consistency(
                fila=fila,
                config=config,
                signal_data_file=output_file,
                baudrate=baudrate,
                timeout=timeout,
                simbank_locks=simbank_locks
            )
            
            if not verification_passed:
                self.logger.error(f"❌ FILA {fila:02d} tiene inconsistencias, reescaneando...")
                # Limpiar resultados de esta fila
                results = [r for r in results if r['fila'] != fila]
                
                # Preparar tareas para re-scan
                rescan_tasks = []
                for bank_idx, bank in enumerate(config.get('simbanks', []), 1):
                    control_port = bank['control_port']
                    modems = bank.get('modems', [])
                    
                    for modem in modems:
                        slot_port = modem['port']
                        col = modem['col']
                        
                        self.logger.info(f"  🔄 Re-scan Pool {bank_idx} | Slot {col} ({slot_port}) -> Fila {fila:04d}")
                        
                        rescan_tasks.append((
                            control_port, col, fila, slot_port,
                            baudrate, timeout, sdata_iteraciones, sdata_intervalo, switch_wait,
                            reboot_stabilization, network_reg_first, network_reg_retry,
                            simbank_locks[control_port], results, results_lock,
                            monitoring_queue, monitoring_lock
                        ))
                
                # Ejecutar re-scan en paralelo con ThreadPoolExecutor
                with ThreadPoolExecutor(max_workers=max_workers) as executor:
                    futures = [executor.submit(self._scan_single_slot, *task) for task in rescan_tasks]
                    for future in futures:
                        future.result()
            
            # Guardar progresivamente cada fila (tiempo real)
            self._save_signal_data_csv(output_file, results)
            
            # RESUMEN DE PROGRESO
            self._print_fila_summary(
                fila=fila,
                total_filas=filas,
                fila_start_time=fila_start_time,
                scan_start_time=scan_start_time,
                total_registros=len(results)
            )
            
            # ESTADÍSTICAS POR FILA
            fila_duration = (datetime.now() - fila_start_time).total_seconds()
            self._save_fila_statistics(
                fila=fila,
                results=results,
                duration=fila_duration,
                max_workers=max_workers
            )
            
            # MONITOREO: Ejecutar para slots que tienen número pero no se registraron (con rotación)
            if monitoring_queue:
                self.logger.info(f"\n📡 Iniciando monitoreo de slots con número sin registro...")
                self._monitor_unregistered_slots(
                    monitoring_queue=monitoring_queue,
                    monitoring_rotation=monitoring_rotation,
                    monitoring_lock=monitoring_lock,
                    simbank_locks=simbank_locks,
                    baudrate=baudrate,
                    timeout=timeout,
                    config=config
                )
        
        # ESTADÍSTICAS FINALES DEL MAPEO
        scan_duration = (datetime.now() - scan_start_time).total_seconds()
        self._save_final_statistics(
            results=results,
            total_duration=scan_duration,
            filas=filas,
            max_workers=max_workers
        )
        
        self.logger.info(f"\n✅ Escaneo completado: {len(results)} SIMs detectadas")
        return results
    
    def _scan_single_slot(self, control_port: str, col: str, fila: int, 
                          slot_port: str, baudrate: int, timeout: int,
                          sdata_iteraciones: int, sdata_intervalo: int, switch_wait: float,
                          reboot_stabilization: float, network_reg_first: float, network_reg_retry: float,
                          simbank_lock: threading.Lock, results: List[Dict],
                          results_lock: threading.Lock,
                          monitoring_queue: Dict, monitoring_lock: threading.Lock):
        """
        Escanea un único slot (ejecutado en hilo separado).
        Realiza múltiples iteraciones y selecciona los mejores valores.
        
        Args:
            control_port: Puerto del SimBank
            col: Columna (01-08)
            fila: Fila actual
            slot_port: Puerto del módem
            baudrate: Baudrate de comunicación
            timeout: Timeout AT
            sdata_iteraciones: Número de veces que se escanea el slot
            sdata_intervalo: Segundos de espera entre iteraciones
            switch_wait: Segundos de espera después de AT+SWIT
            simbank_lock: Lock del SimBank
            results: Lista compartida de resultados
            results_lock: Lock para proteger lista de resultados
            monitoring_queue: Dict para acumular slots que necesitan monitoreo
            monitoring_lock: Lock para proteger monitoring_queue
        """
        try:
            # FASE 1: Conmutación de Hardware
            switch_start = datetime.now()
            success = self._switch_sim(
                control_port=control_port,
                col=col,
                fila=fila,
                lock=simbank_lock
            )
            switch_duration = (datetime.now() - switch_start).total_seconds()
            
            if not success:
                self.logger.warning(f"    [{slot_port}] ⚠️  Fallo en conmutación ({switch_duration:.2f}s)")
                return
            
            # Calcular sleep dinámico: switch_wait - tiempo ya consumido
            elapsed = switch_duration
            remaining_wait = max(0.1, switch_wait - elapsed)  # Mínimo 0.1s
            
            # Esperar cambio físico en SimBank (ajustado por tiempo ya consumido)
            self.logger.info(f"    [{slot_port}] ⏳ Esperando cambio físico ({remaining_wait:.1f}s)... [Switch: {switch_duration:.2f}s]")
            time.sleep(remaining_wait)
            
            # Abrir conexión serial del slot ANTES del reboot
            try:
                ser = serial.Serial(
                    port=slot_port,
                    baudrate=baudrate,
                    timeout=timeout
                )
                time.sleep(0.5)
                elapsed += remaining_wait + 0.5
            except serial.SerialException as e:
                self.logger.warning(f"    [{slot_port}] ⚠️  Puerto ocupado o inaccesible: {e}")
                return
            
            # Detectar modelo del módem
            model = self._detect_model(ser)
            elapsed += 0.2  # Estimado para detect_model
            self.logger.info(f"    [{slot_port}] 🔧 Modelo: {model}")
            
            # REBOOT MANDATORIO según modelo (justo después de AT+SWIT)
            total_elapsed = (datetime.now() - switch_start).total_seconds()
            self.logger.info(f"    [{slot_port}] 🔄 Reiniciando módem... [Total desde switch: {total_elapsed:.2f}s]")
            
            reboot_start = datetime.now()
            if not self._reset_radio(ser, model):
                self.logger.warning(f"    [{slot_port}] ⚠️  Fallo en reboot")
                ser.close()
                return
            
            # OPTIMIZACIÓN DE PARALELISMO: Esperar solo 1s y dejar que el worker procese otros slots
            # Mientras este slot se estabiliza, el worker estará ocupado con otros puertos
            # Al regresar a este slot, ya habrán pasado los 15s necesarios
            reboot_elapsed = (datetime.now() - reboot_start).total_seconds()
            quick_wait = 1.0  # Espera mínima antes de liberar el worker
            
            self.logger.info(f"    [{slot_port}] ⏳ Liberando worker (1s)... [Reboot: {reboot_elapsed:.2f}s]")
            time.sleep(quick_wait)
            
            # Staggered Wait (Módulo 1) - CRÍTICO para evitar RF Jamming
            col_num = int(col)
            delay = (col_num - 1) * 3
            if delay > 0:
                self.logger.info(f"    [{slot_port}] ⏳ Staggered wait ({delay}s)...")
                time.sleep(delay)
            
            # VERIFICACIÓN DE ESTABILIZACIÓN: Verificar si ya pasó el tiempo necesario
            time_since_reboot = (datetime.now() - reboot_start).total_seconds()
            remaining_stabilization = max(0, reboot_stabilization - time_since_reboot)
            
            if remaining_stabilization > 0:
                self.logger.info(f"    [{slot_port}] ⏳ Esperando estabilización restante ({remaining_stabilization:.1f}s)... [Desde reboot: {time_since_reboot:.1f}s]")
                time.sleep(remaining_stabilization)
            else:
                self.logger.info(f"    [{slot_port}] ✅ Ya estabilizado ({time_since_reboot:.1f}s desde reboot)")
            
            # FASE 2: Múltiples iteraciones para obtener mejores valores
            self.logger.info(f"    [{slot_port}] 🔁 Iniciando {sdata_iteraciones} iteraciones...")
            samples = []
            
            for iteration in range(sdata_iteraciones):
                self.logger.info(f"    [{slot_port}] 📊 Iteración {iteration + 1}/{sdata_iteraciones}...")
                
                # Recolectar datos de esta iteración
                sim_data = self._collect_sim_data_with_serial(
                    ser=ser,
                    slot_port=slot_port,
                    fila=fila,
                    col=col,
                    model=model,
                    show_log=(iteration == 0),
                    network_reg_first=network_reg_first,
                    network_reg_retry=network_reg_retry
                )
                
                if sim_data:
                    samples.append(sim_data)
                
                # Esperar antes de la siguiente iteración (excepto en la última)
                if iteration < sdata_iteraciones - 1:
                    time.sleep(sdata_intervalo)
            
            ser.close()
            
            # Seleccionar los mejores valores de todas las muestras
            if samples:
                best_data = self._select_best_values(samples, slot_port)
                
                # Agregar a resultados de forma thread-safe
                with results_lock:
                    results.append(best_data)
                
                # Verificar si necesita monitoreo: tiene número pero no se registró
                numero = best_data.get('numero', 'N/A')
                creg = best_data.get('creg', '0')
                ccid = best_data.get('ccid', 'N/A')
                
                if numero and numero != 'N/A' and creg not in ['1', '5']:
                    # Agregar a cola de monitoreo
                    with monitoring_lock:
                        if slot_port not in monitoring_queue:
                            monitoring_queue[slot_port] = []
                        
                        monitoring_queue[slot_port].append({
                            'pool_com': control_port,
                            'fila': fila,
                            'col': col,
                            'ccid': ccid,
                            'numero': numero
                        })
                    
                    self.logger.info(f"    [{slot_port}] 📝 Agregado a cola de monitoreo (tiene número, sin registro)")
            else:
                self.logger.error(f"    [{slot_port}] ❌ No se obtuvieron muestras válidas")
        
        except Exception as e:
            self.logger.error(f"    [{slot_port}] ❌ Error en escaneo: {e}")
    
    def _print_fila_summary(self, fila: int, total_filas: int, 
                           fila_start_time: datetime, scan_start_time: datetime,
                           total_registros: int):
        """
        Imprime resumen de progreso después de completar una fila.
        
        Args:
            fila: Número de fila completada
            total_filas: Total de filas a escanear
            fila_start_time: Timestamp de inicio de esta fila
            scan_start_time: Timestamp de inicio del escaneo completo
            total_registros: Total de registros guardados hasta ahora
        """
        now = datetime.now()
        
        # Calcular tiempos
        fila_duration = (now - fila_start_time).total_seconds()
        total_elapsed = (now - scan_start_time).total_seconds()
        
        # Estimación de tiempo restante (basado en promedio por fila)
        avg_per_fila = total_elapsed / fila
        filas_restantes = total_filas - fila
        estimated_remaining = avg_per_fila * filas_restantes
        estimated_finish = now + timedelta(seconds=estimated_remaining)
        
        # Colores ANSI
        GREEN = '\033[92m'
        CYAN = '\033[96m'
        YELLOW = '\033[93m'
        MAGENTA = '\033[95m'
        BOLD = '\033[1m'
        RESET = '\033[0m'
        
        # Formato de tiempos
        def format_duration(seconds):
            hours = int(seconds // 3600)
            minutes = int((seconds % 3600) // 60)
            secs = int(seconds % 60)
            if hours > 0:
                return f"{hours}h {minutes}m {secs}s"
            elif minutes > 0:
                return f"{minutes}m {secs}s"
            else:
                return f"{secs}s"
        
        # Progreso porcentual
        progress_pct = (fila / total_filas) * 100
        
        # Barra de progreso
        bar_width = 30
        filled = int(bar_width * fila / total_filas)
        bar = '█' * filled + '░' * (bar_width - filled)
        
        # Imprimir resumen
        self.logger.info(f"\n{BOLD}{'═' * 70}{RESET}")
        self.logger.info(f"{BOLD}{CYAN}📊 RESUMEN FILA {fila:02d}/{total_filas}{RESET}")
        self.logger.info(f"{BOLD}{'═' * 70}{RESET}")
        
        self.logger.info(f"\n{BOLD}⏱️  TIEMPOS:{RESET}")
        self.logger.info(f"   └─ Fila actual:       {YELLOW}{format_duration(fila_duration)}{RESET}")
        self.logger.info(f"   └─ Transcurrido:      {CYAN}{format_duration(total_elapsed)}{RESET}")
        self.logger.info(f"   └─ Estimado restante: {MAGENTA}{format_duration(estimated_remaining)}{RESET}")
        
        self.logger.info(f"\n{BOLD}📅 FECHA Y HORA:{RESET}")
        self.logger.info(f"   └─ Actual:            {now.strftime('%Y-%m-%d %H:%M:%S')}")
        self.logger.info(f"   └─ Fin estimado:      {GREEN}{estimated_finish.strftime('%Y-%m-%d %H:%M:%S')}{RESET}")
        
        self.logger.info(f"\n{BOLD}📈 PROGRESO:{RESET}")
        self.logger.info(f"   └─ {bar} {GREEN}{progress_pct:.1f}%{RESET}")
        self.logger.info(f"   └─ Registros guardados: {CYAN}{total_registros}{RESET}")
        
        self.logger.info(f"\n{BOLD}{'═' * 70}{RESET}\n")
    
    def _switch_sim(self, control_port: str, col: str, fila: int, lock: threading.Lock) -> bool:
        """
        Ejecuta comando AT+SWIT en el SimBank.
        Lock MÍNIMO: solo durante escritura/lectura serial (~0.5s).
        
        Args:
            control_port: Puerto COM del SimBank
            col: Columna (01-08)
            fila: Fila (1-16)
            lock: Lock del SimBank (protege acceso serial a control_port)
            
        Returns:
            True si exitoso
        """
        lock_wait_start = datetime.now()
        
        try:
            # Lock SOLO durante acceso al puerto serial del SimBank
            with lock:
                lock_acquired = datetime.now()
                lock_wait = (lock_acquired - lock_wait_start).total_seconds()
                
                ser = serial.Serial(
                    port=control_port,
                    baudrate=115200,
                    timeout=2
                )
                
                # Comando: AT+SWIT[CC]-[FFFF]
                cmd = f"AT+SWIT{col}-{fila:04d}\r\n"
                ser.write(cmd.encode())
                time.sleep(0.5)  # Espera mínima para respuesta
                
                response = ser.read(100).decode('utf-8', errors='ignore')
                ser.close()
                
                lock_held = (datetime.now() - lock_acquired).total_seconds()
            # Lock liberado aquí - otros workers pueden continuar
            
            if lock_wait > 0.1:  # Log solo si esperó >100ms
                self.logger.info(f"    [LOCK {control_port}] Espera: {lock_wait:.2f}s | Duración: {lock_held:.2f}s")
            
            return 'OK' in response
            
        except Exception as e:
            self.logger.error(f"    ❌ Error SimBank {control_port}: {e}")
            return False
    
    def _verify_fila_consistency(self, fila: int, config: Dict, signal_data_file: str,
                                 baudrate: int, timeout: int, simbank_locks: Dict) -> bool:
        """
        Verifica que los CCID registrados en signal_data.csv coincidan con los CCID reales.
        Lee signal_data.csv, compara con lectura AT+CCID real.
        
        Args:
            fila: Número de fila a verificar
            config: Configuración completa
            signal_data_file: Ruta al CSV de signal_data
            baudrate: Baudrate serial
            timeout: Timeout serial
            simbank_locks: Locks por SimBank
            
        Returns:
            True si todos los CCID coinciden, False si hay inconsistencias
        """
        self.logger.info(f"  📋 Verificando CCID de fila {fila:02d} contra signal_data.csv (paralelo)...")
        
        # Cargar signal_data.csv
        expected_data = {}
        try:
            with open(signal_data_file, 'r', encoding='utf-8') as f:
                reader = csv.DictReader(f)
                for row in reader:
                    if int(row['fila']) == fila:
                        port = row['port']
                        expected_data[port] = {
                            'ccid': row['ccid'],
                            'col': row['col'],
                            'pool_com': None  # Lo obtendremos del config
                        }
        except Exception as e:
            self.logger.warning(f"  ⚠️  No se pudo leer signal_data.csv: {e}")
            return True  # Asumir válido si no hay CSV aún
        
        if not expected_data:
            self.logger.warning(f"  ℹ️  No hay datos esperados para fila {fila:02d} en CSV")
            return True
        
        # Obtener pool_com para cada puerto desde config
        for bank in config.get('simbanks', []):
            pool_com = bank['control_port']
            for modem in bank.get('modems', []):
                port = modem['port']
                if port in expected_data:
                    expected_data[port]['pool_com'] = pool_com
        
        # Preparar tareas de verificación
        max_workers = config.get('max_workers', 8)
        results = {}
        results_lock = threading.Lock()
        verify_tasks = []
        
        for port, expected in expected_data.items():
            verify_tasks.append((
                port,
                expected['pool_com'],
                expected['col'],
                fila,
                expected['ccid'],
                baudrate,
                timeout,
                simbank_locks[expected['pool_com']],
                results,
                results_lock
            ))
        
        # Ejecutar verificaciones en paralelo con ThreadPoolExecutor
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            futures = [executor.submit(self._verify_single_ccid, *task) for task in verify_tasks]
            for future in futures:
                future.result()
        
        # Revisar resultados
        all_match = all(results.values())
        return all_match
    
    def _verify_single_ccid(self, port: str, pool_com: str, col: str, fila: int,
                           expected_ccid: str, baudrate: int, timeout: int,
                           simbank_lock: threading.Lock, results: Dict, results_lock: threading.Lock):
        """
        Verifica el CCID de un slot específico (ejecutado en thread).
        
        Args:
            port: Puerto del módem
            pool_com: Puerto del SimBank
            col: Columna
            fila: Fila
            expected_ccid: CCID esperado
            baudrate: Baudrate serial
            timeout: Timeout serial
            simbank_lock: Lock del SimBank
            results: Dict compartido de resultados {port: True/False}
            results_lock: Lock para proteger results
        """
        try:
            # Switch al slot específico con timing dinámico
            switch_start = datetime.now()
            switch_wait = 3.0  # Tiempo objetivo desde switch hasta lectura CCID
            
            with simbank_lock:
                try:
                    # AT+SWIT
                    ser_pool = serial.Serial(pool_com, 115200, timeout=2)
                    cmd = f"AT+SWIT{col}-{fila:04d}\r\n"
                    ser_pool.write(cmd.encode())
                    time.sleep(0.5)
                    ser_pool.read(100)
                    ser_pool.close()
                
                except Exception as e:
                    self.logger.warning(f"  ⚠️  [{port}] Error en switch: {e}")
                    with results_lock:
                        results[port] = False
                    return
            
            # Timing dinámico: calcular espera restante desde switch
            switch_elapsed = (datetime.now() - switch_start).total_seconds()
            remaining_wait = max(0.1, switch_wait - switch_elapsed)
            time.sleep(remaining_wait)
            
            # Leer CCID real
            try:
                ser_slot = serial.Serial(port, baudrate, timeout=timeout)
                time.sleep(0.3)  # Reducido de 0.5s a 0.3s
                ser_slot.write(b'AT+CCID\r\n')
                time.sleep(0.8)  # Reducido de 1s a 0.8s - suficiente para CCID
                response = ser_slot.read(200).decode('utf-8', errors='ignore')
                ser_slot.close()
                
                # Extraer CCID
                actual_ccid = 'N/A'
                for line in response.split('\n'):
                    if '+CCID:' in line or '+ICCID:' in line:
                        match = re.search(r'(\d{19,20})', line)
                        if match:
                            actual_ccid = match.group(1)
                            break
                
                # Comparar
                if actual_ccid != expected_ccid:
                    self.logger.error(f"  ❌ [{port}] CCID mismatch: esperado={expected_ccid}, real={actual_ccid}")
                    with results_lock:
                        results[port] = False
                else:
                    self.logger.info(f"  ✅ [{port}] CCID correcto: {actual_ccid}")
                    with results_lock:
                        results[port] = True
            
            except Exception as e:
                self.logger.warning(f"  ⚠️  [{port}] Error leyendo CCID: {e}")
                with results_lock:
                    results[port] = False
        
        except Exception as e:
            self.logger.warning(f"  ⚠️  [{port}] Error en verificación: {e}")
            with results_lock:
                results[port] = False
    
    def _collect_sim_data(self, slot_port: str, fila: int, col: str, 
                          baudrate: int, timeout: int) -> Optional[Dict]:
        """
        Recolecta datos de una SIM específica usando comandos AT.
        
        Returns:
            Diccionario con datos de la SIM o None si falla
        """
        try:
            ser = serial.Serial(
                port=slot_port,
                baudrate=baudrate,
                timeout=timeout
            )
            
            time.sleep(0.5)
            
            # Detectar modelo del módem
            model = self._detect_model(ser)
            
            # Reinicio obligatorio según modelo (Módulo 1)
            reboot_start = datetime.now()
            if not self._reset_radio(ser, model):
                ser.close()
                return None
            
            # Timing dinámico: ajustar espera según tiempo consumido en reboot
            network_reg_first = self.config.get('network_registration_first_seconds', 20)
            reboot_elapsed = (datetime.now() - reboot_start).total_seconds()
            remaining_wait = max(0.5, network_reg_first - reboot_elapsed)
            
            # Esperar registro en red
            time.sleep(remaining_wait)
            
            # Recolectar datos
            numero = self._get_phone_number(ser)
            activacion_ts = self._get_activation_date(ser)
            ccid = self._get_ccid(ser)
            csq = self._get_signal_quality(ser)
            op_red, creg = self._get_network_status(ser)
            
            ser.close()
            
            # Estructura CSV: timestamp,port,model,ccid,op_simid,op_red,fila,csq,dbm,col,numero,creg,unixtimestamp
            return {
                'timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                'port': slot_port,
                'model': model,
                'ccid': ccid,
                'op_simid': '',  # Se obtiene del operador si es necesario
                'op_red': op_red,
                'fila': fila,
                'csq': csq,
                'dbm': self._csq_to_dbm(csq),
                'col': col,
                'numero': numero,
                'creg': creg,
                'unixtimestamp': activacion_ts
            }
            
        except serial.SerialException as e:
            self.logger.warning(f"    ⚠️  Puerto {slot_port} ocupado o inaccesible: {e}")
            return None
        except Exception as e:
            self.logger.error(f"    ❌ Error en {slot_port}: {e}")
            return None
    
    def _detect_model(self, ser: serial.Serial) -> str:
        """Detecta el modelo del módem (EC25/UC20)."""
        try:
            ser.write(b'ATI\r\n')
            time.sleep(1)
            response = ser.read(200).decode('utf-8', errors='ignore')
            
            if 'EC25' in response:
                return 'EC25'
            elif 'UC20' in response:
                return 'UC20'
            return 'UNKNOWN'
        except:
            return 'UNKNOWN'
    
    def _reset_radio(self, ser: serial.Serial, model: str) -> bool:
        """
        Reinicia la radio según el modelo (Regla de Oro - Módulo 1).
        
        EC25: AT+CFUN=0 -> AT+CFUN=1
        UC20: AT+CFUN=1,1
        """
        try:
            if model == 'EC25':
                # Modo avión
                ser.write(b'AT+CFUN=0\r\n')
                time.sleep(1)
                response = ser.read(100).decode('utf-8', errors='ignore')
                
                if 'OK' not in response:
                    self.logger.warning(f"    ⚠️  AT+CFUN=0 sin OK")
                
                # Encender
                ser.write(b'AT+CFUN=1\r\n')
                time.sleep(1)
                response = ser.read(100).decode('utf-8', errors='ignore')
                
                if 'OK' not in response:
                    self.logger.warning(f"    ⚠️  AT+CFUN=1 sin OK")
                
            elif model == 'UC20':
                # Reset directo
                ser.write(b'AT+CFUN=1,1\r\n')
                time.sleep(1)
                response = ser.read(100).decode('utf-8', errors='ignore')
                
                if 'OK' not in response:
                    self.logger.warning(f"    ⚠️  AT+CFUN=1,1 sin OK")
            
            return True
        except:
            return False
    
    def _collect_sim_data_with_serial(self, ser: serial.Serial, slot_port: str, 
                                      fila: int, col: str, model: str, show_log: bool = True,
                                      network_reg_first: float = 20, network_reg_retry: float = 5) -> Optional[Dict]:
        """
        Recolecta datos de una SIM usando un serial ya abierto y reiniciado.
        
        Args:
            show_log: Si True, muestra logs detallados
        
        Returns:
            Diccionario con datos de la SIM o None si falla
        """
        try:
            # Timing dinámico: esperar registro en red según tiempo consumido
            wait_start = datetime.now()
            if show_log:
                self.logger.info(f"    [{slot_port}] ⏳ Esperando registro en red ({network_reg_first}s)...")
                time.sleep(network_reg_first)
            else:
                # En iteraciones subsiguientes, usar tiempo reducido
                self.logger.info(f"    [{slot_port}] ⏳ Esperando registro en red ({network_reg_retry}s)...")
                time.sleep(network_reg_retry)
            
            wait_elapsed = (datetime.now() - wait_start).total_seconds()
            
            # Recolectar datos
            numero = self._get_phone_number(ser)
            activacion_ts = self._get_activation_date(ser)
            ccid = self._get_ccid(ser)
            csq = self._get_signal_quality(ser)
            op_red, creg = self._get_network_status(ser)
            
            if show_log:
                self.logger.info(f"    [{slot_port}] ✅ Datos: CCID={ccid}, Número={numero}, CREG={creg}, CSQ={csq}, Unix={activacion_ts}")
            
            # Estructura CSV: timestamp,port,model,ccid,op_simid,op_red,fila,csq,dbm,col,numero,creg,unixtimestamp
            return {
                'timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                'port': slot_port,
                'model': model,
                'ccid': ccid,
                'op_simid': '',  # Se obtiene del operador si es necesario
                'op_red': op_red,
                'fila': fila,
                'csq': csq,
                'dbm': self._csq_to_dbm(csq),
                'col': col,
                'numero': numero,
                'creg': creg,
                'unixtimestamp': activacion_ts
            }
            
        except Exception as e:
            if show_log:
                self.logger.error(f"    ❌ Error recolectando datos en {slot_port}: {e}")
            return None
    
    def _select_best_values(self, samples: List[Dict], slot_port: str) -> Dict:
        """
        Selecciona los mejores valores de múltiples muestras.
        
        Lógica:
        - Strings (op_red, numero, etc.): Elegir el que NO sea "N/A" o vacío
        - CREG: Preferir 1 o 5 (registrado)
        - CSQ: Elegir el más alto
        - CCID: Debe ser consistente en todas las muestras
        
        Args:
            samples: Lista de diccionarios con datos recolectados
            slot_port: Puerto para logging
            
        Returns:
            Diccionario con los mejores valores
        """
        if not samples:
            return {}
        
        # Usar la primera muestra como base
        best = samples[0].copy()
        
        # Asegurar que unixtimestamp existe (compatibilidad con archivos antiguos)
        if 'unixtimestamp' not in best:
            best['unixtimestamp'] = '0'
        
        self.logger.info(f"    [{slot_port}] 🎯 Seleccionando mejores valores de {len(samples)} muestras...")
        
        # Verificar CCID consistente
        ccids = set(s.get('ccid', 'N/A') for s in samples if s.get('ccid') != 'N/A')
        if len(ccids) > 1:
            self.logger.warning(f"    [{slot_port}] ⚠️  CCID inconsistente entre muestras: {ccids}")
        
        # STRINGS: Elegir el que NO sea N/A
        for field in ['op_red', 'numero', 'unixtimestamp']:
            for sample in samples:
                value = sample.get(field, 'N/A')
                if field == 'unixtimestamp':
                    # Para unixtimestamp, elegir el que NO sea 0 o N/A
                    if value and value != 'N/A' and value != '0':
                        best[field] = value
                        break
                else:
                    # Para otros campos string
                    if value and value != 'N/A' and value.strip():
                        best[field] = value
                        break  # Tomar el primero válido
        
        # CREG: Preferir 1 o 5 (registrado)
        for sample in samples:
            creg = sample.get('creg', '0')
            if creg in ['1', '5']:
                best['creg'] = creg
                break
        
        # CSQ: Elegir el más alto
        csq_values = [int(s.get('csq', 0)) for s in samples if s.get('csq', '0').isdigit()]
        if csq_values:
            best_csq = max(csq_values)
            best['csq'] = best_csq
            best['dbm'] = self._csq_to_dbm(best_csq)
        
        # Timestamp: usar el más reciente
        best['timestamp'] = samples[-1]['timestamp']
        
        self.logger.info(f"    [{slot_port}] ✅ Mejor: CREG={best.get('creg')}, CSQ={best.get('csq')}, Op={best.get('op_red')}")
        
        return best
    
    def _get_phone_number(self, ser: serial.Serial) -> str:
        """Obtiene el número telefónico usando AT+CPBR=1."""
        try:
            ser.write(b'AT+CPBR=1\r\n')
            time.sleep(1)
            response = ser.read(200).decode('utf-8', errors='ignore')
            
            # Buscar número con regex: +CPBR: 1,"número",...
            match = re.search(r'\+CPBR:\s*1,"([^"]+)"', response)
            if match:
                return match.group(1)
            
            # Fallback: buscar patrón de número chileno
            match = re.search(r'(\+?56\d{9}|\d{8,9})', response)
            if match:
                return match.group(1)
                
            return 'N/A'
        except:
            return 'N/A'
    
    def _get_activation_date(self, ser: serial.Serial) -> str:
        """Obtiene fecha de activación desde AT+CPBR=2 (Unix Timestamp)."""
        try:
            ser.write(b'AT+CPBR=2\r\n')
            time.sleep(1)
            response = ser.read(200).decode('utf-8', errors='ignore')
            
            # Buscar timestamp en la respuesta
            match = re.search(r'(\d{10,})', response)
            if match:
                return match.group(1)
            
            return '0'
        except:
            return '0'
    
    def _get_ccid(self, ser: serial.Serial) -> str:
        """Obtiene CCID (ICCID de la SIM)."""
        try:
            ser.write(b'AT+CCID\r\n')
            time.sleep(1)
            response = ser.read(200).decode('utf-8', errors='ignore')
            
            match = re.search(r'(\d{19,20})', response)
            if match:
                return match.group(1)
            
            return 'N/A'
        except:
            return 'N/A'
    
    def _get_signal_quality(self, ser: serial.Serial) -> str:
        """Obtiene calidad de señal (CSQ)."""
        try:
            ser.write(b'AT+CSQ\r\n')
            time.sleep(1)
            response = ser.read(200).decode('utf-8', errors='ignore')
            
            match = re.search(r'\+CSQ:\s*(\d+),', response)
            if match:
                return match.group(1)
            
            return 'N/A'
        except:
            return 'N/A'
    
    def _get_network_status(self, ser: serial.Serial) -> Tuple[str, str]:
        """
        Obtiene operador y estado de registro.
        
        Returns:
            Tupla (operador, creg_status)
        """
        operador = 'N/A'
        creg = 'N/A'
        
        try:
            # AT+COPS=3,2 para configurar formato numérico (MCC+MNC)
            ser.write(b'AT+COPS=3,2\r\n')
            time.sleep(1)
            ser.read(200)  # Limpiar respuesta OK
            
            # AT+COPS? para obtener operador en formato numérico
            ser.write(b'AT+COPS?\r\n')
            time.sleep(1)
            response = ser.read(200).decode('utf-8', errors='ignore')
            
            # Buscar formato: +COPS: 0,2,"73003",7
            # Captura el ID numérico del operador (MCC+MNC)
            match = re.search(r'\+COPS:\s*\d+,\d+,"(\d+)"', response)
            if match:
                operador = match.group(1)
            
            # AT+CREG? para estado de registro
            ser.write(b'AT+CREG?\r\n')
            time.sleep(1)
            response = ser.read(200).decode('utf-8', errors='ignore')
            
            match = re.search(r'\+CREG:\s*\d+,(\d+)', response)
            if match:
                creg = match.group(1)
        except:
            pass
        
        return operador, creg
    
    def _csq_to_dbm(self, csq_str: str) -> str:
        """
        Convierte CSQ (0-31) a dBm aproximado.
        
        Args:
            csq_str: String del CSQ (ej: "25", "99")
            
        Returns:
            String del dBm (ej: "-62", "-113")
        """
        try:
            csq = int(csq_str)
            
            if csq == 99 or csq == 0:
                return '-113'  # Sin señal
            elif 1 <= csq <= 31:
                # Fórmula: dBm = -113 + (csq * 2)
                dbm = -113 + (csq * 2)
                return str(dbm)
            else:
                return '-113'
        except:
            return '-113'
    
    def _monitor_unregistered_slots(self, monitoring_queue: Dict, monitoring_rotation: Dict[str, int],
                                    monitoring_lock: threading.Lock,
                                    simbank_locks: Dict, baudrate: int, timeout: int, config: Dict):
        """
        Monitorea slots que tienen número pero no se registraron.
        Ejecuta UNA SOLA verificación en paralelo para ver si cambió el CREG.
        Usa rotación para alternar entre filas del mismo slot.
        
        Args:
            monitoring_queue: Dict {slot_com: [{pool_com, fila, col, ccid, numero}, ...]}
            monitoring_rotation: Dict {slot_port: rotation_index} - índice para rotar filas
            monitoring_lock: Lock para proteger monitoring_queue
            simbank_locks: Locks por SimBank
            baudrate: Baudrate serial
            timeout: Timeout serial
            config: Configuración completa
        """
        with monitoring_lock:
            if not monitoring_queue:
                return
            
            self.logger.info(f"  📊 {len(monitoring_queue)} slots en cola de monitoreo")
        
        # Parámetros de monitoreo (solo 1 check)
        sim_intento_operativo = config.get('sim_intento_operativo', 3)
        max_workers = config.get('max_workers', 8)
        
        start_time = datetime.now()
        self.logger.info(f"  ⏱️  [{start_time.strftime('%H:%M:%S')}] Monitoreo: 1 verificación única por slot (max_workers={max_workers})")
        
        # Preparar tareas de monitoreo con rotación
        monitor_tasks = []
        for slot_port in monitoring_queue.keys():
            # Obtener índice de rotación actual (0 si es primera vez)
            rotation_index = monitoring_rotation.get(slot_port, 0)
            
            monitor_tasks.append((
                slot_port,
                monitoring_queue[slot_port],
                simbank_locks,
                baudrate,
                timeout,
                config,
                rotation_index
            ))
            
            # Incrementar índice de rotación para próxima iteración
            monitoring_rotation[slot_port] = rotation_index + 1
        
        # Ejecutar monitoreo en paralelo con ThreadPoolExecutor
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            # Lanzar todos los threads en paralelo
            futures = [executor.submit(self._monitor_single_slot, *task) for task in monitor_tasks]
            
            # Esperar a que todos terminen (en paralelo, no secuencial)
            for future in as_completed(futures):
                try:
                    future.result()  # Capturar excepciones si las hay
                except Exception as e:
                    self.logger.error(f"  ❌ Error en thread de monitoreo: {e}")
        
        end_time = datetime.now()
        duration = (end_time - start_time).total_seconds()
        self.logger.info(f"  ✅ [{end_time.strftime('%H:%M:%S')}] Monitoreo completado para {len(monitor_tasks)} slots en {duration:.1f}s")
    
    def _monitor_single_slot(self, slot_port: str, fila_configs: List[Dict],
                             simbank_locks: Dict, baudrate: int, timeout: int, config: Dict,
                             rotation_index: int):
        """
        Monitorea un slot específico UNA SOLA VEZ para verificar si cambió el CREG.
        Usa rotación para alternar entre filas cuando hay múltiples en el mismo slot.
        
        Args:
            slot_port: Puerto del módem a monitorear
            fila_configs: Lista de configuraciones [{pool_com, fila, col, ccid, numero}, ...]
            simbank_locks: Locks por SimBank
            baudrate: Baudrate serial
            timeout: Timeout serial
            config: Configuración completa
            rotation_index: Índice de rotación para seleccionar qué fila verificar
        """
        switch_wait = config.get('switch_wait_seconds', 3.2)
        start = datetime.now()
        try:
            total_filas = len(fila_configs)
            # Seleccionar fila actual basada en rotación
            current_index = rotation_index % total_filas
            fila_config = fila_configs[current_index]
            
            if total_filas > 1:
                self.logger.info(f"  🔍 [{start.strftime('%H:%M:%S')}] [{slot_port}] Verificando fila {current_index + 1}/{total_filas} (rotación)")
            else:
                self.logger.info(f"  🔍 [{start.strftime('%H:%M:%S')}] [{slot_port}] Verificando 1 fila")
            
            pool_com = fila_config['pool_com']
            fila = fila_config['fila']
            col = fila_config['col']
            ccid = fila_config['ccid']
            numero = fila_config['numero']
            
            self.logger.info(f"  📡 [{slot_port}] Verificando Fila {fila:02d}, Col {col}")
            
            # PASO 1: Switch a esta fila/col (MINIMIZAR tiempo dentro del lock)
            switch_start = datetime.now()
            with simbank_locks[pool_com]:
                try:
                    ser_pool = serial.Serial(pool_com, 115200, timeout=2)
                    cmd = f"AT+SWIT{col}-{fila:04d}\r\n"
                    ser_pool.write(cmd.encode())
                    time.sleep(0.5)  # Mínimo necesario para comando
                    ser_pool.read(100)
                    ser_pool.close()
                except Exception as e:
                    self.logger.warning(f"  ⚠️  [{slot_port}] Error en switch: {e}")
                    return
            # Lock liberado aquí - otros threads pueden usar el SimBank
            
            # Timing dinámico: esperar el tiempo restante hasta switch_wait
            switch_elapsed = (datetime.now() - switch_start).total_seconds()
            remaining_switch = max(0.1, switch_wait - switch_elapsed)
            time.sleep(remaining_switch)
            
            # PASO 2: Reboot del módem
            reboot_start = datetime.now()
            self.logger.info(f"  🔄 [{slot_port}] Reiniciando módem...")
            try:
                ser_slot = serial.Serial(slot_port, baudrate, timeout=timeout)
                time.sleep(0.3)
                
                # Comando de reboot
                ser_slot.write(b'AT+CFUN=1,1\r\n')
                time.sleep(0.3)
                ser_slot.read(100)
                
                ser_slot.close()
            except Exception as e:
                self.logger.warning(f"  ⚠️  [{slot_port}] Error en reboot: {e}")
                return
            
            # PASO 3: Esperar estabilización del reboot
            reboot_stabilization = config.get('reboot_stabilization_seconds', 15)
            reboot_elapsed = (datetime.now() - reboot_start).total_seconds()
            remaining_stabilization = max(0.1, reboot_stabilization - reboot_elapsed)
            
            if remaining_stabilization > 1:
                self.logger.info(f"  ⏳ [{slot_port}] Esperando estabilización ({remaining_stabilization:.1f}s)...")
            time.sleep(remaining_stabilization)
            
            # PASO 4: Esperar registro de red
            network_reg_first = config.get('network_registration_first_seconds', 20)
            reg_start = datetime.now()
            self.logger.info(f"  📡 [{slot_port}] Esperando registro de red ({network_reg_first}s)...")
            
            time.sleep(network_reg_first)
            
            # PASO 5: Verificar CREG
            try:
                ser_slot = serial.Serial(slot_port, baudrate, timeout=timeout)
                time.sleep(0.3)
                
                ser_slot.write(b'AT+CREG?\r\n')
                time.sleep(0.8)
                response = ser_slot.read(200).decode('utf-8', errors='ignore')
                
                ser_slot.close()
                
                # Extraer CREG
                creg = '0'
                for line in response.split('\n'):
                    if '+CREG:' in line:
                        parts = line.split(',')
                        if len(parts) >= 2:
                            creg = parts[1].strip()
                            break
                
                end = datetime.now()
                duration = (end - start).total_seconds()
                
                self.logger.info(f"  📶 [{end.strftime('%H:%M:%S')}] [{slot_port}] CREG={creg}, Número={numero}, CCID={ccid} (duración: {duration:.1f}s)")
                
                # Reportar resultado
                if creg in ['1', '5']:
                    self.logger.info(f"  ✅ [{slot_port}] Ahora está registrado!")
                else:
                    self.logger.warning(f"  ⚠️  [{slot_port}] Sigue sin registro (CREG={creg})")
            
            except Exception as e:
                end = datetime.now()
                duration = (end - start).total_seconds()
                self.logger.warning(f"  ⚠️  [{end.strftime('%H:%M:%S')}] [{slot_port}] Error leyendo CREG: {e} ({duration:.1f}s)")
        
        except Exception as e:
            end = datetime.now()
            duration = (end - start).total_seconds()
            self.logger.error(f"  ❌ [{end.strftime('%H:%M:%S')}] [{slot_port}] Error en monitoreo: {e} ({duration:.1f}s)")
    
    def _generate_output_files(self):
        """
        Genera archivos de salida después de completar signal_data.csv:
        - numero_simid.txt (con validaciones y filtros)
        - lista_pos.json
        - Copia a output_identities si está configurado
        """
        self.logger.info("\n📄 Generando archivos de salida...")
        
        # --- 1. Generar numero_simid.txt ---
        numero_simid_path = os.path.join(self.data_dir, 'numero_simid.txt')
        numero_simid_dict = {}
        invalid_count = 0
        duplicate_count = 0
        
        for row in self.signal_data:
            numero = row.get('numero')
            ccid = row.get('ccid')
            creg = str(row.get('creg', ''))
            
            # Filtros básicos
            if not numero or numero == 'N/A':
                continue
            if not ccid or ccid == 'N/A':
                continue
            if creg not in ['1', '5']:
                continue
            
            # Validación de formato por país
            if not self._validar_numero_por_pais(numero, ccid):
                invalid_count += 1
                continue
            
            # Verificar duplicados
            if numero in numero_simid_dict:
                duplicate_count += 1
                continue
            
            numero_simid_dict[numero] = ccid
        
        # Guardar numero_simid.txt
        numero_simid_lines = [f"{num}={cid}" for num, cid in numero_simid_dict.items()]
        
        try:
            with open(numero_simid_path, 'w', encoding='utf-8') as f:
                f.write('\n'.join(numero_simid_lines))
            self.logger.info(f"✅ Generado: numero_simid.txt ({len(numero_simid_lines)} líneas)")
            if invalid_count > 0:
                self.logger.warning(f"   ⚠️  Rechazados por formato inválido: {invalid_count}")
            if duplicate_count > 0:
                self.logger.warning(f"   ⚠️  Rechazados por duplicados: {duplicate_count}")
        except Exception as e:
            self.logger.error(f"❌ Error al generar numero_simid.txt: {e}")
        
        # --- 2. Generar lista_pos.json ---
        try:
            from slot_logic import SlotManager
            slot_manager = SlotManager(data_manager=self)
            lista_pos = slot_manager.slot_positions
            
            # Simplificar estructura
            lista_pos_simplified = {}
            for port, positions in lista_pos.items():
                lista_pos_simplified[port] = [
                    {
                        'fila': pos.get('fila'),
                        'col': pos.get('col'),
                        'numero': pos.get('numero'),
                        'ccid': pos.get('ccid'),
                        'creg': pos.get('creg')
                    }
                    for pos in positions
                ]
            
            lista_pos_path = os.path.join(self.data_dir, 'lista_pos.json')
            with open(lista_pos_path, 'w', encoding='utf-8') as f:
                json.dump(lista_pos_simplified, f, indent=2, ensure_ascii=False)
            
            self.logger.info(f"✅ Generado: lista_pos.json ({len(lista_pos_simplified)} puertos)")
        except Exception as e:
            self.logger.error(f"❌ Error al generar lista_pos.json: {e}")
        
        # --- 3. Copiar a output_identities si está configurado ---
        output_path = self.config_manager.get_path('output_identities')
        
        if output_path:
            try:
                os.makedirs(os.path.dirname(output_path), exist_ok=True)
                
                # Copiar numero_simid.txt a output_identities
                import shutil
                shutil.copy(numero_simid_path, output_path)
                
                self.logger.info(f"✅ Copiado a output_identities: {output_path}")
            except Exception as e:
                self.logger.error(f"❌ Error al copiar a output_identities: {e}")
        else:
            self.logger.warning("ℹ️  output_identities no configurado, omitiendo copia")
    
    def _validar_numero_por_pais(self, numero: str, ccid: str) -> bool:
        """
        Valida formato del número según país indicado en CCID.
        
        CCID format: 89 [COUNTRY_CODE] [...]
        Posiciones 2-5 indican país:
        - 560 = Chile (56)
        - 570 = Colombia (57)
        
        Args:
            numero: Número telefónico
            ccid: CCID de la SIM
            
        Returns:
            True si el formato es válido
        """
        if not numero or not ccid or len(ccid) < 5:
            return False
        
        # Extraer código de país del CCID
        country_code = ccid[2:5]
        
        # Validaciones por país
        if country_code == '560':  # Chile
            # Formato: 569XXXXXXXX (celular) o 562XXXXXXXX (fijo)
            # Total: 11 dígitos
            if not numero.startswith('56'):
                return False
            if len(numero) != 11:
                return False
            if not numero[2] in ['9', '2', '3', '4', '5', '6', '7']:
                return False
            return numero.isdigit()
            
        elif country_code == '570':  # Colombia
            # Formato: 57XXXXXXXXXX (10 dígitos después del 57)
            # Total: 12 dígitos
            if not numero.startswith('57'):
                return False
            if len(numero) != 12:
                return False
            return numero.isdigit()
        
        else:
            # País no reconocido - validación genérica
            # Mínimo 8 dígitos, máximo 15, debe ser numérico
            if not numero.isdigit():
                return False
            if len(numero) < 8 or len(numero) > 15:
                return False
            return True
    
    def _export_identities(self):
        """Exporta lista_sim_actual.txt con los números telefónicos."""
        output_path = self.config_manager.get_path('output_identities')
        
        if not output_path:
            self.logger.warning("⚠️  No se definió 'output_identities' en config.json")
            return
        
        try:
            # Crear directorio si no existe
            os.makedirs(os.path.dirname(output_path), exist_ok=True)
            
            # Extraer números válidos
            numeros = [
                item['numero'] 
                for item in self.signal_data 
                if item.get('numero') and item['numero'] != 'N/A'
            ]
            
            with open(output_path, 'w', encoding='utf-8') as f:
                f.write('\n'.join(numeros))
            
            self.logger.info(f"✅ Exportado: {output_path} ({len(numeros)} números)")
            
        except Exception as e:
            self.logger.error(f"❌ Error al exportar identidades: {e}")
    
    def _save_signal_data_csv(self, filepath: str, data: List[Dict]) -> None:
        """
        Guarda signal_data en formato CSV.
        
        Args:
            filepath: Ruta del archivo CSV
            data: Lista de diccionarios con datos de SIMs
        """
        if not data:
            return
            
        # Orden de columnas CSV
        fieldnames = ['timestamp', 'port', 'model', 'ccid', 'op_simid', 'op_red', 
                     'fila', 'csq', 'dbm', 'col', 'numero', 'creg', 'unixtimestamp']
        
        with open(filepath, 'w', newline='', encoding='utf-8') as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(data)
    
    def _load_signal_data_csv(self, filepath: str) -> List[Dict]:
        """
        Carga signal_data desde formato CSV.
        
        Args:
            filepath: Ruta del archivo CSV
            
        Returns:
            Lista de diccionarios con datos de SIMs
        """
        data = []
        with open(filepath, 'r', encoding='utf-8') as f:
            reader = csv.DictReader(f)
            for row in reader:
                row_dict = dict(row)
                # Asegurar compatibilidad: si no existe unixtimestamp, asignar 0
                if 'unixtimestamp' not in row_dict or not row_dict.get('unixtimestamp'):
                    row_dict['unixtimestamp'] = '0'
                data.append(row_dict)
        return data
    
    def _mirror_data_files(self) -> None:
        """
        Duplica archivos de data/ a ubicación espejo si está configurado.
        Lee config['mirror_signal_data']. Permite especificar:
        - Directorio: 'C:\\backup\\' → Crea archivos con nombre original
        - Path completo: 'C:\\backup\\mi_signal_data.csv' → Usa nombre personalizado
        
        Si no existe, es vacío o null, no hace nada.
        """
        import shutil
        
        mirror_path = self.config.get('mirror_signal_data')
        
        if not mirror_path or mirror_path.strip() == '':
            return
        
        # Expandir ~ y rutas relativas
        mirror_path = os.path.expanduser(mirror_path)
        mirror_path = os.path.abspath(mirror_path)
        
        try:
            data_dir = os.path.join(os.getcwd(), 'data')
            
            # Determinar si es directorio o archivo completo
            is_directory = mirror_path.endswith(('\\', '/')) or os.path.isdir(mirror_path)
            
            if is_directory:
                # Caso 1: Es un directorio → Duplicar con nombres originales
                os.makedirs(mirror_path, exist_ok=True)
                files_to_mirror = ['signal_data.csv', 'slot_state.json']
                
                for filename in files_to_mirror:
                    src = os.path.join(data_dir, filename)
                    if os.path.exists(src):
                        dst = os.path.join(mirror_path, filename)
                        shutil.copy2(src, dst)
                        self.logger.info(f"🔄 Duplicado: {filename} → {mirror_path}")
            else:
                # Caso 2: Es un path de archivo completo → Solo signal_data.csv con nombre personalizado
                mirror_dir = os.path.dirname(mirror_path)
                custom_filename = os.path.basename(mirror_path)
                
                os.makedirs(mirror_dir, exist_ok=True)
                
                # Solo duplicar signal_data.csv con el nombre personalizado
                src = os.path.join(data_dir, 'signal_data.csv')
                if os.path.exists(src):
                    shutil.copy2(src, mirror_path)
                    self.logger.info(f"🔄 Duplicado: signal_data.csv → {mirror_path}")
                
                # slot_state.json se guarda con nombre original en mismo directorio
                src_state = os.path.join(data_dir, 'slot_state.json')
                if os.path.exists(src_state):
                    dst_state = os.path.join(mirror_dir, 'slot_state.json')
                    shutil.copy2(src_state, dst_state)
                    self.logger.info(f"🔄 Duplicado: slot_state.json → {mirror_dir}")
        
        except Exception as e:
            self.logger.warning(f"⚠️  Error al duplicar archivos: {e}")
    
    def _save_fila_statistics(self, fila: int, results: List[Dict], duration: float, max_workers: int):
        """Guarda estadísticas detalladas de una fila en archivo JSON"""
        try:
            stats_file = os.path.join(self.data_dir, 'mapeo_statistics.json')
            
            # Calcular métricas de la fila
            total_slots = len([r for r in results if r.get('fila') == fila])
            con_numero = len([r for r in results if r.get('fila') == fila and r.get('numero') and r.get('numero') != 'NO_NUMERO'])
            con_registro = len([r for r in results if r.get('fila') == fila and r.get('numero') and r.get('numero') != 'NO_NUMERO' and r.get('creg') and r.get('creg') not in ['0', '4', 'NO_CREG']])
            solo_numero_sin_registro = con_numero - con_registro
            
            pct_con_numero = (con_numero / total_slots * 100) if total_slots > 0 else 0
            pct_con_registro = (con_registro / total_slots * 100) if total_slots > 0 else 0
            pct_solo_numero = (solo_numero_sin_registro / total_slots * 100) if total_slots > 0 else 0
            
            # Workers efectivos estimados
            avg_slot_duration = duration / total_slots if total_slots > 0 else 0
            workers_efectivos = total_slots / (duration / avg_slot_duration) if avg_slot_duration > 0 else 0
            
            fila_stats = {
                'fila': fila,
                'timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                'duracion_segundos': round(duration, 2),
                'total_slots': total_slots,
                'con_numero': con_numero,
                'con_registro': con_registro,
                'solo_numero_sin_registro': solo_numero_sin_registro,
                'porcentaje_con_numero': round(pct_con_numero, 2),
                'porcentaje_con_registro': round(pct_con_registro, 2),
                'porcentaje_solo_numero_sin_registro': round(pct_solo_numero, 2),
                'workers_configurados': max_workers,
                'workers_efectivos_estimados': round(workers_efectivos, 2),
                'tiempo_promedio_por_slot': round(avg_slot_duration, 2)
            }
            
            # Cargar estadísticas existentes
            all_stats = {'filas': [], 'resumen_final': {}}
            if os.path.exists(stats_file):
                with open(stats_file, 'r', encoding='utf-8') as f:
                    all_stats = json.load(f)
            
            # Agregar estadísticas de esta fila
            all_stats['filas'].append(fila_stats)
            
            # Guardar
            with open(stats_file, 'w', encoding='utf-8') as f:
                json.dump(all_stats, f, indent=2, ensure_ascii=False)
            
            # Log resumen
            self.logger.info(f"\n📊 ESTADÍSTICAS FILA {fila}:")
            self.logger.info(f"   ✅ Con número Y registro: {con_registro}/{total_slots} ({pct_con_registro:.1f}%)")
            self.logger.info(f"   📱 Solo número sin registro: {solo_numero_sin_registro}/{total_slots} ({pct_solo_numero:.1f}%)")
            self.logger.info(f"   ⏱️  Duración: {duration:.1f}s | Promedio: {avg_slot_duration:.1f}s/slot")
            self.logger.info(f"   🔧 Workers efectivos: {workers_efectivos:.1f}/{max_workers}")
            
        except Exception as e:
            self.logger.error(f"❌ Error guardando estadísticas de fila: {e}")
    
    def _save_final_statistics(self, results: List[Dict], total_duration: float, filas: int, max_workers: int):
        """Guarda estadísticas finales del mapeo completo"""
        try:
            stats_file = os.path.join(self.data_dir, 'mapeo_statistics.json')
            
            # Calcular métricas totales
            total_slots = len(results)
            con_numero = len([r for r in results if r.get('numero') and r.get('numero') != 'NO_NUMERO'])
            con_registro = len([r for r in results if r.get('numero') and r.get('numero') != 'NO_NUMERO' and r.get('creg') and r.get('creg') not in ['0', '4', 'NO_CREG']])
            solo_numero_sin_registro = con_numero - con_registro
            sin_numero = total_slots - con_numero
            
            pct_con_numero = (con_numero / total_slots * 100) if total_slots > 0 else 0
            pct_con_registro = (con_registro / total_slots * 100) if total_slots > 0 else 0
            pct_solo_numero = (solo_numero_sin_registro / total_slots * 100) if total_slots > 0 else 0
            pct_sin_numero = (sin_numero / total_slots * 100) if total_slots > 0 else 0
            
            # Workers efectivos estimados
            avg_slot_duration = total_duration / total_slots if total_slots > 0 else 0
            workers_efectivos = (total_slots * avg_slot_duration) / total_duration if total_duration > 0 else 0
            
            # Distribución por operador
            operadores = {}
            for r in results:
                op = r.get('op_red', 'DESCONOCIDO')
                operadores[op] = operadores.get(op, 0) + 1
            
            # Distribución por CSQ
            csq_ranges = {'Excelente (>20)': 0, 'Bueno (15-20)': 0, 'Regular (10-14)': 0, 'Malo (<10)': 0, 'Sin señal': 0}
            for r in results:
                try:
                    csq = int(r.get('csq', 0))
                    if csq == 0 or csq == 99:
                        csq_ranges['Sin señal'] += 1
                    elif csq > 20:
                        csq_ranges['Excelente (>20)'] += 1
                    elif csq >= 15:
                        csq_ranges['Bueno (15-20)'] += 1
                    elif csq >= 10:
                        csq_ranges['Regular (10-14)'] += 1
                    else:
                        csq_ranges['Malo (<10)'] += 1
                except:
                    csq_ranges['Sin señal'] += 1
            
            final_stats = {
                'timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                'duracion_total_segundos': round(total_duration, 2),
                'duracion_total_minutos': round(total_duration / 60, 2),
                'filas_escaneadas': filas,
                'total_slots': total_slots,
                'slots_por_fila': total_slots // filas if filas > 0 else 0,
                'con_numero': con_numero,
                'con_registro': con_registro,
                'solo_numero_sin_registro': solo_numero_sin_registro,
                'sin_numero': sin_numero,
                'porcentaje_con_numero': round(pct_con_numero, 2),
                'porcentaje_con_registro': round(pct_con_registro, 2),
                'porcentaje_solo_numero_sin_registro': round(pct_solo_numero, 2),
                'porcentaje_sin_numero': round(pct_sin_numero, 2),
                'workers_configurados': max_workers,
                'workers_efectivos_estimados': round(workers_efectivos, 2),
                'eficiencia_workers_pct': round((workers_efectivos / max_workers * 100), 2) if max_workers > 0 else 0,
                'tiempo_promedio_por_slot': round(avg_slot_duration, 2),
                'tiempo_promedio_por_fila': round(total_duration / filas, 2) if filas > 0 else 0,
                'distribucion_operadores': operadores,
                'distribucion_calidad_señal': csq_ranges
            }
            
            # Cargar y actualizar archivo
            all_stats = {'filas': [], 'resumen_final': {}}
            if os.path.exists(stats_file):
                with open(stats_file, 'r', encoding='utf-8') as f:
                    all_stats = json.load(f)
            
            all_stats['resumen_final'] = final_stats
            
            # Guardar
            with open(stats_file, 'w', encoding='utf-8') as f:
                json.dump(all_stats, f, indent=2, ensure_ascii=False)
            
            # Log resumen final
            self.logger.info(f"\n{'='*80}")
            self.logger.info(f"📊 ESTADÍSTICAS FINALES DEL MAPEO")
            self.logger.info(f"{'='*80}")
            self.logger.info(f"⏱️  Duración total: {total_duration:.1f}s ({total_duration/60:.1f}min)")
            self.logger.info(f"📍 Filas escaneadas: {filas} | Total slots: {total_slots}")
            self.logger.info(f"")
            self.logger.info(f"📱 DISTRIBUCIÓN DE NÚMEROS:")
            self.logger.info(f"   ✅ Con número Y registro: {con_registro}/{total_slots} ({pct_con_registro:.1f}%)")
            self.logger.info(f"   📱 Solo número sin registro: {solo_numero_sin_registro}/{total_slots} ({pct_solo_numero:.1f}%)")
            self.logger.info(f"   📞 Total con número: {con_numero}/{total_slots} ({pct_con_numero:.1f}%)")
            self.logger.info(f"   ❌ Sin número: {sin_numero}/{total_slots} ({pct_sin_numero:.1f}%)")
            self.logger.info(f"")
            self.logger.info(f"🔧 RENDIMIENTO:")
            self.logger.info(f"   Workers efectivos: {workers_efectivos:.1f}/{max_workers} ({final_stats['eficiencia_workers_pct']:.1f}%)")
            self.logger.info(f"   Tiempo promedio/slot: {avg_slot_duration:.1f}s")
            self.logger.info(f"   Tiempo promedio/fila: {final_stats['tiempo_promedio_por_fila']:.1f}s")
            self.logger.info(f"")
            self.logger.info(f"📡 OPERADORES:")
            for op, count in sorted(operadores.items(), key=lambda x: x[1], reverse=True):
                pct = (count / total_slots * 100) if total_slots > 0 else 0
                self.logger.info(f"   {op}: {count} ({pct:.1f}%)")
            self.logger.info(f"")
            self.logger.info(f"📶 CALIDAD DE SEÑAL:")
            for quality, count in csq_ranges.items():
                pct = (count / total_slots * 100) if total_slots > 0 else 0
                self.logger.info(f"   {quality}: {count} ({pct:.1f}%)")
            self.logger.info(f"")
            self.logger.info(f"💾 Estadísticas guardadas en: {stats_file}")
            self.logger.info(f"{'='*80}\n")
            
        except Exception as e:
            self.logger.error(f"❌ Error guardando estadísticas finales: {e}")

