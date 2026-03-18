#!/usr/bin/env python3
"""
Conversor de dict_nodo a config.json simbanks.

Este script convierte archivos dict_nodo (con 2 o 4 pools) a la estructura
simbanks de config.json, manteniendo todos los demás campos intactos.
"""

import argparse
import json
import sys
from pathlib import Path
from typing import Dict, List, Any


# ============================================================================
# CONFIGURACIÓN - RUTAS DE ARCHIVOS
# ============================================================================
INPUT_FILE = "~\\Documents\\sadmin_ext\\json\\dict_nodo\\dict_nodo.json"
OUTPUT_FILE = "config.json"
# ============================================================================


def load_json_file(file_path: Path) -> Dict[str, Any]:
    """
    Carga un archivo JSON y retorna su contenido.
    
    Args:
        file_path: Ruta al archivo JSON
        
    Returns:
        Diccionario con el contenido del archivo
        
    Raises:
        FileNotFoundError: Si el archivo no existe
        json.JSONDecodeError: Si el JSON es inválido
    """
    with open(file_path, 'r', encoding='utf-8') as f:
        return json.load(f)


def convert_dict_nodo_to_simbanks(dict_nodo: Dict[str, List[str]]) -> List[Dict[str, Any]]:
    """
    Convierte la estructura dict_nodo a la estructura simbanks.
    
    Args:
        dict_nodo: Diccionario con control_port como clave y lista de puertos como valor
        
    Returns:
        Lista de simbanks en el formato requerido por config.json
    """
    simbanks = []
    
    for control_port, modem_ports in dict_nodo.items():
        modems = []
        for idx, port in enumerate(modem_ports, start=1):
            modems.append({
                "port": port,
                "col": f"{idx:02d}"  # Formato 01, 02, 03, etc.
            })
        
        simbanks.append({
            "control_port": control_port,
            "modems": modems
        })
    
    return simbanks


def update_config_with_simbanks(
    config_data: Dict[str, Any],
    dict_nodo_data: Dict[str, List[str]]
) -> Dict[str, Any]:
    """
    Actualiza la configuración con los nuevos simbanks, manteniendo otros campos.
    
    Args:
        config_data: Configuración actual
        dict_nodo_data: Datos del dict_nodo a convertir
        
    Returns:
        Configuración actualizada
    """
    new_simbanks = convert_dict_nodo_to_simbanks(dict_nodo_data)
    config_data['simbanks'] = new_simbanks
    return config_data


def save_json_file(file_path: Path, data: Dict[str, Any], indent: int = 2) -> None:
    """
    Guarda datos en un archivo JSON.
    
    Args:
        file_path: Ruta donde guardar el archivo
        data: Datos a guardar
        indent: Espacios de indentación (default: 2)
    """
    with open(file_path, 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=indent, ensure_ascii=False)


def main() -> int:
    """
    Función principal del programa.
    
    Returns:
        Código de salida (0: éxito, 1: error)
    """
    parser = argparse.ArgumentParser(
        description='Convierte dict_nodo a estructura simbanks en config.json',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Ejemplos de uso:
  %(prog)s
  %(prog)s -i dict_nodo_4_pool.json -o new_config.json
        """
    )
    
    parser.add_argument(
        '-i', '--input',
        type=str,
        default=INPUT_FILE,
        help=f'Ruta al archivo dict_nodo de entrada (default: {INPUT_FILE})'
    )
    
    parser.add_argument(
        '-o', '--output',
        type=str,
        default=OUTPUT_FILE,
        help=f'Ruta al archivo config.json de salida (default: {OUTPUT_FILE})'
    )
    
    parser.add_argument(
        '-v', '--verbose',
        action='store_true',
        help='Muestra información detallada del proceso'
    )
    
    args = parser.parse_args()
    
    # Convertir rutas a Path objects y expandir ~ (home directory)
    input_path = Path(args.input).expanduser()
    output_path = Path(args.output).expanduser()
    
    # Verificar que el archivo de entrada existe
    if not input_path.exists():
        print(f"Error: El archivo de entrada '{input_path}' no existe.", file=sys.stderr)
        return 1
    
    if not input_path.is_file():
        print(f"Error: '{input_path}' no es un archivo.", file=sys.stderr)
        return 1
    
    try:
        # Cargar dict_nodo
        if args.verbose:
            print(f"Cargando dict_nodo desde: {input_path}")
        
        dict_nodo_data = load_json_file(input_path)
        
        if args.verbose:
            print(f"  - Encontrados {len(dict_nodo_data)} control ports")
        
        # Cargar config existente o crear uno nuevo
        if output_path.exists():
            if args.verbose:
                print(f"Cargando config existente desde: {output_path}")
            config_data = load_json_file(output_path)
        else:
            if args.verbose:
                print(f"Creando nueva configuración (archivo no existe)")
            # Configuración base mínima
            config_data = {
                "filas": 16,
                "baudrate": 115200,
                "at_timeout": 1,
                "cambio_fila_minutos": 30,
                "sim_intento_operativo": 5,
                "sdata_iteraciones": 2,
                "sdata_intervalo_iteracion_segundos": 4,
                "switch_wait_seconds": 3.2,
                "reboot_stabilization_seconds": 15,
                "network_registration_first_seconds": 20,
                "network_registration_retry_seconds": 5,
                "max_workers": 16,
                "output_identities": "~\\Documents\\sadmin_ext\\numeros\\lista_sim_actual.txt",
                "mirror_signal_data": "",
                "simclient_exec_path": "~\\AppData\\Local\\HeroSMS-Partners\\HeroSMS-Partners.exe"
            }
        
        # Actualizar con nuevos simbanks
        if args.verbose:
            print("Convirtiendo dict_nodo a simbanks...")
        
        updated_config = update_config_with_simbanks(config_data, dict_nodo_data)
        
        # Guardar configuración actualizada
        if args.verbose:
            print(f"Guardando configuración actualizada en: {output_path}")
        
        save_json_file(output_path, updated_config)
        
        print(f"✓ Conversión completada exitosamente")
        print(f"  Input:  {input_path}")
        print(f"  Output: {output_path}")
        print(f"  Simbanks generados: {len(updated_config['simbanks'])}")
        
        return 0
        
    except json.JSONDecodeError as e:
        print(f"Error: Archivo JSON inválido - {e}", file=sys.stderr)
        return 1
    except Exception as e:
        print(f"Error inesperado: {e}", file=sys.stderr)
        if args.verbose:
            import traceback
            traceback.print_exc()
        return 1


if __name__ == '__main__':
    sys.exit(main())
