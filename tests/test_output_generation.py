"""
Test para generación de archivos de salida: numero_simid y lista_pos.
Verifica que los formatos son correctos y que los archivos se crean apropiadamente.
"""
import os
import sys
import csv
import json
import tempfile
from pathlib import Path

# Agregar src al path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

from slot_logic import SlotManager


def test_numero_simid_format():
    """
    Test 1: Verifica formato numero_simid (numero=ccid).
    Cada línea debe tener: numero=CCID
    Con validación de integridad y sin duplicados (solo creg=1 o 5)
    """
    print("\n" + "="*60)
    print("TEST 1: Formato numero_simid")
    print("="*60)
    
    # Buscar signal_data.csv en data/
    signal_data_path = os.path.join(os.getcwd(), 'data', 'signal_data.csv')
    
    if not os.path.exists(signal_data_path):
        print(f"❌ signal_data.csv no encontrado en: {signal_data_path}")
        return False
    
    # Cargar signal_data
    with open(signal_data_path, 'r', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        signal_data = [dict(row) for row in reader]
    
    print(f"📊 Registros totales en signal_data.csv: {len(signal_data)}")
    
    # Función de validación de número según país del CCID
    def validar_numero_por_pais(numero, ccid):
        if not numero or not ccid or len(ccid) < 5:
            return False
        country_code = ccid[2:5]
        
        if country_code == '560':  # Chile
            if not numero.startswith('56'):
                return False
            if len(numero) != 11:
                return False
            if not numero[2] in ['9', '2', '3', '4', '5', '6', '7']:
                return False
            return numero.isdigit()
        elif country_code == '570':  # Colombia
            if not numero.startswith('57'):
                return False
            if len(numero) != 12:
                return False
            return numero.isdigit()
        else:  # País no reconocido
            if not numero.isdigit():
                return False
            if len(numero) < 8 or len(numero) > 15:
                return False
            return True
    
    # Filtrar SIMs válidas (creg = 1 o 5) con validación de integridad
    valid_dict = {}
    invalid_count = 0
    duplicate_count = 0
    creg_rejected = 0
    
    for row in signal_data:
        numero = row.get('numero')
        ccid = row.get('ccid')
        creg = str(row.get('creg', ''))
        
        # Validar que existan
        if not numero or numero == 'N/A' or numero == '':
            continue
        if not ccid or ccid == 'N/A' or ccid == '':
            continue
        
        # Validar creg (1 o 5)
        if creg not in ['1', '5']:
            creg_rejected += 1
            continue
        
        # Validar formato del número según país
        if not validar_numero_por_pais(numero, ccid):
            invalid_count += 1
            continue
        
        # Verificar duplicados
        if numero in valid_dict:
            duplicate_count += 1
            continue
        
        valid_dict[numero] = ccid
    
    print(f"✅ SIMs válidas encontradas: {len(valid_dict)}")
    print(f"   Rechazados por formato inválido: {invalid_count}")
    print(f"   Rechazados por duplicados: {duplicate_count}")
    print(f"   Rechazados por creg (no 1 ni 5): {creg_rejected}")
    
    # Mostrar primeras 5
    valid_lines = [f"{num}={cid}" for num, cid in list(valid_dict.items())[:5]]
    print("\n📝 Primeras 5 líneas de numero_simid:")
    for i, line in enumerate(valid_lines, 1):
        print(f"  {i}. {line}")
    
    print(f"✅ Sin duplicados: {len(valid_dict)} números únicos")
    
    return len(valid_dict) > 0


def test_lista_pos_format():
    """
    Test 2: Verifica formato lista_pos (posiciones por puerto).
    Formato: JSON con {port: [lista de slots válidos]}
    """
    print("\n" + "="*60)
    print("TEST 2: Formato lista_pos por puerto")
    print("="*60)
    
    # Inicializar SlotManager (usa signal_data.csv automáticamente)
    try:
        slot_manager = SlotManager()
    except Exception as e:
        print(f"❌ Error al inicializar SlotManager: {e}")
        return False
    
    # Obtener slot_positions (es el equivalente a lista_pos)
    lista_pos = slot_manager.slot_positions
    
    print(f"📊 Puertos con SIMs válidas: {len(lista_pos)}")
    
    # Mostrar resumen por puerto
    print("\n📍 Posiciones válidas por puerto:")
    for port in sorted(lista_pos.keys()):
        positions = lista_pos[port]
        filas = [pos.get('fila') for pos in positions]
        print(f"  {port}: {len(positions)} posiciones → Filas: {filas}")
    
    # Verificar estructura
    for port, positions in lista_pos.items():
        for pos in positions:
            # Cada posición debe tener: port, col, fila, numero, ccid
            required_keys = ['port', 'col', 'fila', 'numero', 'ccid']
            missing_keys = [k for k in required_keys if k not in pos]
            
            if missing_keys:
                print(f"❌ {port}: Faltan claves {missing_keys} en posición")
                return False
    
    print("✅ Todas las posiciones tienen estructura válida")
    return len(lista_pos) > 0


def test_generate_output_files():
    """
    Test 3: Genera archivos de salida reales.
    - data/numero_simid.txt (solo creg=1 o 5, con validaciones)
    - data/lista_sim_actual.txt (todos los creg, con validaciones) 
    - data/lista_pos.json
    """
    print("\n" + "="*60)
    print("TEST 3: Generación de archivos de salida")
    print("="*60)
    
    # Buscar signal_data.csv
    signal_data_path = os.path.join(os.getcwd(), 'data', 'signal_data.csv')
    
    if not os.path.exists(signal_data_path):
        print(f"❌ signal_data.csv no encontrado")
        return False
    
    # Cargar signal_data
    with open(signal_data_path, 'r', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        signal_data = [dict(row) for row in reader]
    
    # Función de validación de número según país del CCID
    def validar_numero_por_pais(numero, ccid):
        if not numero or not ccid or len(ccid) < 5:
            return False
        country_code = ccid[2:5]
        
        if country_code == '560':  # Chile
            if not numero.startswith('56'):
                return False
            if len(numero) != 11:
                return False
            if not numero[2] in ['9', '2', '3', '4', '5', '6', '7']:
                return False
            return numero.isdigit()
        elif country_code == '570':  # Colombia
            if not numero.startswith('57'):
                return False
            if len(numero) != 12:
                return False
            return numero.isdigit()
        else:
            if not numero.isdigit():
                return False
            if len(numero) < 8 or len(numero) > 15:
                return False
            return True
    
    # --- Generar numero_simid.txt (solo creg=1 o 5) ---
    numero_simid_dict = {}
    for row in signal_data:
        numero = row.get('numero')
        ccid = row.get('ccid')
        creg = str(row.get('creg', ''))
        
        if not numero or numero == 'N/A':
            continue
        if not ccid or ccid == 'N/A':
            continue
        if creg not in ['1', '5']:
            continue
        if not validar_numero_por_pais(numero, ccid):
            continue
        if numero in numero_simid_dict:
            continue
        
        numero_simid_dict[numero] = ccid
    
    numero_simid_lines = [f"{num}={cid}" for num, cid in numero_simid_dict.items()]
    
    # Guardar numero_simid.txt
    output_dir = os.path.join(os.getcwd(), 'data')
    os.makedirs(output_dir, exist_ok=True)
    
    numero_simid_path = os.path.join(output_dir, 'numero_simid.txt')
    with open(numero_simid_path, 'w', encoding='utf-8') as f:
        f.write('\n'.join(numero_simid_lines))
    
    print(f"✅ Generado: {numero_simid_path}")
    print(f"   Líneas: {len(numero_simid_lines)} (solo creg=1 o 5)")
    
    # --- Generar lista_pos.json ---
    slot_manager = SlotManager()
    lista_pos = slot_manager.slot_positions
    
    # Convertir a formato más simple (solo info esencial)
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
    
    lista_pos_path = os.path.join(output_dir, 'lista_pos.json')
    with open(lista_pos_path, 'w', encoding='utf-8') as f:
        json.dump(lista_pos_simplified, f, indent=2, ensure_ascii=False)
    
    print(f"✅ Generado: {lista_pos_path}")
    print(f"   Puertos: {len(lista_pos_simplified)}")
    
    # Mostrar contenido de ejemplo
    print(f"\n📄 Primeras 5 líneas de numero_simid.txt (formato: numero=CCID):")
    for i, line in enumerate(numero_simid_lines[:5], 1):
        print(f"   {i}. {line}")
    
    print(f"\n📄 Ejemplo de lista_pos.json (primer puerto):")
    first_port = sorted(lista_pos_simplified.keys())[0]
    print(f"   {first_port}: {lista_pos_simplified[first_port][0]}")
    
    return True


def test_lista_sim_actual():
    """
    Test 4: Verifica que lista_sim_actual.txt se genera correctamente.
    Este archivo contiene numero=CCID con validación de integridad.
    - Sin duplicados
    - Números con formato válido según país del CCID
    """
    print("\n" + "="*60)
    print("TEST 4: Formato lista_sim_actual.txt")
    print("="*60)
    
    # Buscar signal_data.csv
    signal_data_path = os.path.join(os.getcwd(), 'data', 'signal_data.csv')
    
    if not os.path.exists(signal_data_path):
        print(f"❌ signal_data.csv no encontrado")
        return False
    
    # Cargar signal_data
    with open(signal_data_path, 'r', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        signal_data = [dict(row) for row in reader]
    
    # Función de validación de número según país del CCID
    def validar_numero_por_pais(numero, ccid):
        """
        Valida formato del número según país indicado en CCID.
        
        CCID format: 89 [COUNTRY_CODE] [...]
        Posiciones 2-5 (índices 2:5) indican país:
        - 560 = Chile (56)
        - 570 = Colombia (57)
        """
        if not numero or not ccid or len(ccid) < 5:
            return False
        
        # Extraer código de país del CCID (posiciones 3-5)
        country_code = ccid[2:5]
        
        # Validaciones por país
        if country_code == '560':  # Chile
            # Formato: 569XXXXXXXX (celular) o 562XXXXXXXX (fijo)
            # Total: 11 dígitos
            if not numero.startswith('56'):
                return False
            if len(numero) != 11:
                return False
            if not numero[2] in ['9', '2', '3', '4', '5', '6', '7']:  # Prefijos válidos
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
    
    # Extraer y validar números con CCID
    lista_sim_dict = {}  # Usar dict para evitar duplicados
    invalid_count = 0
    duplicate_count = 0
    
    for row in signal_data:
        numero = row.get('numero')
        ccid = row.get('ccid')
        
        # Validar que existan
        if not numero or numero == 'N/A' or numero == '':
            continue
        if not ccid or ccid == 'N/A' or ccid == '':
            continue
        
        # Validar formato del número según país
        if not validar_numero_por_pais(numero, ccid):
            invalid_count += 1
            print(f"⚠️  Número inválido rechazado: {numero} (CCID: {ccid[:7]}...)")
            continue
        
        # Verificar duplicados
        if numero in lista_sim_dict:
            duplicate_count += 1
            print(f"⚠️  Número duplicado rechazado: {numero}")
            continue
        
        lista_sim_dict[numero] = ccid
    
    # Convertir a lista de líneas
    lista_sim_lines = [f"{numero}={ccid}" for numero, ccid in lista_sim_dict.items()]
    
    print(f"📊 Registros válidos: {len(lista_sim_lines)}")
    print(f"   Rechazados por formato inválido: {invalid_count}")
    print(f"   Rechazados por duplicados: {duplicate_count}")
    
    # Guardar lista_sim_actual.txt (en data/ para test)
    output_dir = os.path.join(os.getcwd(), 'data')
    lista_sim_path = os.path.join(output_dir, 'lista_sim_actual.txt')
    
    with open(lista_sim_path, 'w', encoding='utf-8') as f:
        f.write('\n'.join(lista_sim_lines))
    
    print(f"✅ Generado: {lista_sim_path}")
    print(f"   Líneas: {len(lista_sim_lines)}")
    
    # Mostrar primeros 10
    print(f"\n📄 Primeros 10 registros válidos (formato: numero=CCID):")
    for i, line in enumerate(lista_sim_lines[:10], 1):
        print(f"   {i}. {line}")
    
    return len(lista_sim_lines) > 0


if __name__ == '__main__':
    print("="*60)
    print("TEST SUITE: Generación de Archivos de Salida")
    print("="*60)
    
    # Cambiar al directorio mp_simclient
    test_dir = os.path.dirname(os.path.abspath(__file__))
    project_dir = os.path.dirname(test_dir)
    os.chdir(project_dir)
    print(f"📂 Working directory: {os.getcwd()}")
    
    # Ejecutar tests
    results = []
    
    results.append(("numero_simid format", test_numero_simid_format()))
    results.append(("lista_pos format", test_lista_pos_format()))
    results.append(("lista_sim_actual", test_lista_sim_actual()))
    results.append(("generate output files", test_generate_output_files()))
    
    # Resumen
    print("\n" + "="*60)
    print("RESUMEN DE TESTS")
    print("="*60)
    
    passed = sum(1 for _, result in results if result)
    total = len(results)
    
    for test_name, result in results:
        status = "✅ PASS" if result else "❌ FAIL"
        print(f"{status}: {test_name}")
    
    print(f"\n🎯 Total: {passed}/{total} tests pasados")
    
    if passed == total:
        print("✅ Todos los tests pasaron - Archivos generados exitosamente")
    else:
        print("❌ Algunos tests fallaron")
        sys.exit(1)
