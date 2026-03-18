"""
Logger Configuration - Sistema de Logging Rotativo.
Configura logging con rotación de archivos para producción.
"""
import os
import logging
from logging.handlers import RotatingFileHandler
from datetime import datetime


def cleanup_old_logs(log_dir='logs', max_size_gb=5):
    """
    Limpia logs antiguos cuando el directorio supera el tamaño máximo (FIFO).
    
    Args:
        log_dir: Directorio de logs
        max_size_gb: Tamaño máximo en GB antes de limpiar
    """
    if not os.path.exists(log_dir):
        return
    
    try:
        # Calcular tamaño total del directorio
        total_size = 0
        log_files = []
        
        for root, dirs, files in os.walk(log_dir):
            for file in files:
                filepath = os.path.join(root, file)
                try:
                    size = os.path.getsize(filepath)
                    mtime = os.path.getmtime(filepath)
                    total_size += size
                    log_files.append((filepath, mtime, size))
                except OSError:
                    continue
        
        # Convertir a GB
        total_size_gb = total_size / (1024 ** 3)
        
        # Si supera el límite, borrar archivos más antiguos (FIFO)
        if total_size_gb > max_size_gb:
            print(f"⚠️  Logs ocupan {total_size_gb:.2f}GB, limpiando (límite: {max_size_gb}GB)...")
            
            # Ordenar por fecha de modificación (más antiguos primero)
            log_files.sort(key=lambda x: x[1])
            
            # Borrar hasta reducir a 80% del límite
            target_size = max_size_gb * 0.8 * (1024 ** 3)
            current_size = total_size
            deleted_count = 0
            
            for filepath, mtime, size in log_files:
                if current_size <= target_size:
                    break
                
                try:
                    os.remove(filepath)
                    current_size -= size
                    deleted_count += 1
                except OSError as e:
                    print(f"⚠️  Error eliminando {filepath}: {e}")
            
            new_size_gb = current_size / (1024 ** 3)
            print(f"✅ Limpieza completada: {deleted_count} archivos eliminados")
            print(f"   Tamaño reducido: {total_size_gb:.2f}GB → {new_size_gb:.2f}GB")
    
    except Exception as e:
        print(f"⚠️  Error en limpieza de logs: {e}")


def setup_logger(name='mp_simclient', log_dir='logs', level=logging.INFO, verbose_level=0):
    """
    Configura el sistema de logging con rotación de archivos.
    
    Args:
        name: Nombre del logger
        log_dir: Directorio donde guardar los logs
        level: Nivel de logging para archivos (siempre DEBUG)
        verbose_level: Nivel de verbosidad para consola:
                       0 = INFO (default)
                       1 = INFO con más detalles (-v)
                       2 = DEBUG (-vv)
                       3+ = DEBUG con timestamps detallados (-vvv)
        
    Returns:
        Logger configurado
    """
    # Limpiar logs antiguos si superan 5GB
    cleanup_old_logs(log_dir, max_size_gb=5)
    
    # Crear directorio de logs si no existe
    os.makedirs(log_dir, exist_ok=True)
    
    # Determinar nivel de consola según verbosidad
    if verbose_level == 0:
        console_level = logging.INFO  # Default: solo INFO
    elif verbose_level == 1:
        console_level = logging.INFO  # -v: INFO pero con más detalles
    else:
        console_level = logging.DEBUG  # -vv/-vvv: DEBUG completo
    
    # Obtener o crear logger
    logger = logging.getLogger(name)
    logger.setLevel(logging.DEBUG)  # Logger siempre DEBUG (archivo captura todo)
    
    # Evitar duplicación de handlers si ya existe
    if logger.handlers:
        return logger
    
    # Formato para archivo (siempre completo con thread)
    file_formatter = logging.Formatter(
        '%(asctime)s | %(levelname)-8s | %(threadName)-15s | %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )
    
    # Handler para archivo con rotación
    # Máximo 10 MB por archivo, mantener 5 backups
    log_file = os.path.join(log_dir, 'mp_simclient.log')
    file_handler = RotatingFileHandler(
        log_file,
        maxBytes=10 * 1024 * 1024,  # 10 MB
        backupCount=5,
        encoding='utf-8'
    )
    file_handler.setLevel(logging.DEBUG)  # Archivo siempre captura DEBUG
    file_handler.setFormatter(file_formatter)
    
    # Handler para consola (formato según verbosidad)
    console_handler = logging.StreamHandler()
    console_handler.setLevel(console_level)
    
    if verbose_level >= 3:
        # -vvv: Formato más detallado con thread y timestamp completo
        console_formatter = logging.Formatter(
            '%(asctime)s | %(levelname)-8s | %(threadName)-15s | %(message)s',
            datefmt='%Y-%m-%d %H:%M:%S'
        )
    elif verbose_level >= 2:
        # -vv: DEBUG con thread pero timestamp corto
        console_formatter = logging.Formatter(
            '%(asctime)s | %(levelname)-8s | %(threadName)-10s | %(message)s',
            datefmt='%H:%M:%S'
        )
    elif verbose_level >= 1:
        # -v: INFO con timestamp y level
        console_formatter = logging.Formatter(
            '%(asctime)s | %(levelname)-8s | %(message)s',
            datefmt='%H:%M:%S'
        )
    else:
        # Sin -v: Solo timestamp corto y mensaje (más limpio)
        console_formatter = logging.Formatter(
            '%(asctime)s | %(message)s',
            datefmt='%H:%M:%S'
        )
    
    console_handler.setFormatter(console_formatter)
    
    # Agregar handlers al logger
    logger.addHandler(file_handler)
    logger.addHandler(console_handler)
    
    return logger


def log_system_info(logger):
    """
    Registra información del sistema al inicio.
    
    Args:
        logger: Logger configurado
    """
    import platform
    import sys
    
    logger.info("=" * 70)
    logger.info("MP_SIMCLIENT - Sistema de Gestión SIM-Farming")
    logger.info("=" * 70)
    logger.info(f"Fecha/Hora: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    logger.info(f"Sistema: {platform.system()} {platform.release()}")
    logger.info(f"Python: {sys.version.split()[0]}")
    logger.info(f"Directorio de trabajo: {os.getcwd()}")
    logger.info("=" * 70)


def log_config_summary(logger, config_data):
    """
    Registra un resumen de la configuración.
    
    Args:
        logger: Logger configurado
        config_data: Diccionario con configuración
    """
    logger.info("CONFIGURACIÓN CARGADA:")
    logger.info(f"  - Filas: {config_data.get('filas', 'N/A')}")
    logger.info(f"  - Baudrate: {config_data.get('baudrate', 'N/A')}")
    logger.info(f"  - AT Timeout: {config_data.get('at_timeout', 'N/A')}s")
    logger.info(f"  - Cambio de fila: {config_data.get('cambio_fila_minutos', 'N/A')} minutos")
    
    simbanks = config_data.get('simbanks', [])
    logger.info(f"  - SimBanks: {len(simbanks)}")
    
    total_modems = sum(len(bank.get('modems', [])) for bank in simbanks)
    logger.info(f"  - Total Módems: {total_modems}")
    logger.info("-" * 70)
