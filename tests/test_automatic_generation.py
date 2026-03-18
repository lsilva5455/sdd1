"""
Test para validar la generación automática de archivos de salida
después de completar signal_data.csv
"""
import os
import sys
import json
import tempfile
import shutil

# Agregar src al path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

from data_manager import DataManager
from config.config_manager import ConfigManager


def test_automatic_generation_after_scan():
    """
    Test: Verifica que después de generar signal_data.csv se generen automáticamente:
    1. numero_simid.txt (con validaciones)
    2. lista_pos.json
    """
    print("\n" + "="*60)
    print("TEST: Generación Automática Post-Scan")
    print("="*60)
    
    # Usar data/ real
    data_dir = os.path.join(os.getcwd(), 'data')
    
    if not os.path.exists(os.path.join(data_dir, 'signal_data.csv')):
        print("⚠️  signal_data.csv no existe, ejecuta un scan primero")
        return False
    
    # Verificar que existan los archivos generados
    numero_simid_path = os.path.join(data_dir, 'numero_simid.txt')
    lista_pos_path = os.path.join(data_dir, 'lista_pos.json')
    
    # Verificar numero_simid.txt
    if not os.path.exists(numero_simid_path):
        print(f"❌ numero_simid.txt no existe en: {numero_simid_path}")
        return False
    
    # Verificar contenido de numero_simid.txt
    with open(numero_simid_path, 'r', encoding='utf-8') as f:
        lines = f.readlines()
    
    print(f"✅ numero_simid.txt existe ({len(lines)} líneas)")
    
    # Validar formato
    for i, line in enumerate(lines[:5], 1):
        line = line.strip()
        if '=' not in line:
            print(f"❌ Línea {i} sin formato numero=CCID: {line}")
            return False
        
        numero, ccid = line.split('=', 1)
        if len(ccid) < 15:
            print(f"❌ CCID inválido en línea {i}: {ccid}")
            return False
    
    print("✅ Formato numero=CCID válido")
    
    # Verificar que no hay duplicados
    numeros = [line.split('=')[0].strip() for line in lines]
    if len(numeros) != len(set(numeros)):
        print(f"❌ Hay números duplicados")
        return False
    
    print("✅ Sin duplicados")
    
    # Verificar lista_pos.json
    if not os.path.exists(lista_pos_path):
        print(f"❌ lista_pos.json no existe en: {lista_pos_path}")
        return False
    
    with open(lista_pos_path, 'r', encoding='utf-8') as f:
        lista_pos = json.load(f)
    
    print(f"✅ lista_pos.json existe ({len(lista_pos)} puertos)")
    
    # Validar estructura
    for port, positions in lista_pos.items():
        if not isinstance(positions, list):
            print(f"❌ {port} no tiene lista de posiciones")
            return False
        
        for pos in positions:
            required_keys = ['fila', 'col', 'numero', 'ccid', 'creg']
            for key in required_keys:
                if key not in pos:
                    print(f"❌ {port} falta clave {key}")
                    return False
    
    print("✅ Estructura de lista_pos.json válida")
    
    return True


def test_output_identities_copy():
    """
    Test: Verifica que si output_identities está configurado,
    numero_simid.txt se copia a esa ubicación
    """
    print("\n" + "="*60)
    print("TEST: Copia a output_identities")
    print("="*60)
    
    # Cargar config
    try:
        cm = ConfigManager()
        output_path = cm.get_path('output_identities')
    except:
        print("⚠️  No se pudo cargar config.json")
        return False
    
    if not output_path:
        print("ℹ️  output_identities no configurado, test omitido")
        return True
    
    # Verificar que el archivo existe
    if not os.path.exists(output_path):
        print(f"❌ Archivo no copiado a: {output_path}")
        return False
    
    print(f"✅ Archivo copiado a: {output_path}")
    
    # Verificar que el contenido es idéntico
    numero_simid_path = os.path.join(os.getcwd(), 'data', 'numero_simid.txt')
    
    if not os.path.exists(numero_simid_path):
        print("❌ numero_simid.txt no existe en data/")
        return False
    
    with open(numero_simid_path, 'r', encoding='utf-8') as f:
        content_source = f.read()
    
    with open(output_path, 'r', encoding='utf-8') as f:
        content_dest = f.read()
    
    if content_source != content_dest:
        print("❌ El contenido copiado no coincide")
        return False
    
    print("✅ Contenido idéntico")
    
    return True


def test_mirror_signal_data():
    """
    Test: Verifica que si mirror_signal_data está configurado,
    signal_data.csv se copia a esa ubicación
    """
    print("\n" + "="*60)
    print("TEST: Mirror de signal_data.csv")
    print("="*60)
    
    # Cargar config
    try:
        with open(os.path.join(os.getcwd(), 'config.json'), 'r', encoding='utf-8') as f:
            config = json.load(f)
    except:
        print("⚠️  No se pudo cargar config.json")
        return False
    
    mirror_path = config.get('mirror_signal_data')
    
    if not mirror_path or mirror_path == '':
        print("ℹ️  mirror_signal_data no configurado, test omitido")
        return True
    
    # Expandir ruta
    mirror_path = os.path.expanduser(mirror_path)
    
    # Determinar si es directorio o archivo
    if mirror_path.endswith('\\') or mirror_path.endswith('/'):
        # Es directorio
        mirror_file = os.path.join(mirror_path, 'signal_data.csv')
    else:
        # Es archivo personalizado
        mirror_file = mirror_path
    
    # Verificar que existe
    if not os.path.exists(mirror_file):
        print(f"❌ Archivo no copiado a: {mirror_file}")
        return False
    
    print(f"✅ Archivo copiado a: {mirror_file}")
    
    return True


if __name__ == '__main__':
    print("="*60)
    print("TEST SUITE: Generación Automática de Archivos")
    print("="*60)
    
    # Cambiar al directorio mp_simclient
    test_dir = os.path.dirname(os.path.abspath(__file__))
    project_dir = os.path.dirname(test_dir)
    os.chdir(project_dir)
    print(f"📂 Working directory: {os.getcwd()}")
    
    # Ejecutar tests
    results = []
    
    results.append(("Generación automática", test_automatic_generation_after_scan()))
    results.append(("Copia a output_identities", test_output_identities_copy()))
    results.append(("Mirror signal_data", test_mirror_signal_data()))
    
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
        print("✅ Todos los tests pasaron")
    else:
        print("❌ Algunos tests fallaron")
        sys.exit(1)
