"""
Tests Unitarios para SlotLogic.
Verifica rotación circular y persistencia de estado.
"""
import os
import sys
import json
import csv
import unittest
import tempfile
import shutil

# Agregar src al path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

from slot_logic import SlotManager


class TestSlotLogic(unittest.TestCase):
    """Tests para SlotManager."""
    
    def setUp(self):
        """Preparar ambiente de prueba."""
        # Crear directorio temporal
        self.test_dir = tempfile.mkdtemp()
        self.original_cwd = os.getcwd()
        os.chdir(self.test_dir)
        
        # Crear data/ en el temp
        self.data_dir = os.path.join(self.test_dir, 'data')
        os.makedirs(self.data_dir, exist_ok=True)
        
        # Crear signal_data.csv de prueba
        self.test_signal_data = [
            # Puerto COM6 - 3 SIMs válidas
            {
                'timestamp': '2025-01-15 10:00:00',
                'port': 'COM6',
                'model': 'UC20',
                'ccid': '8956030246016341461F',
                'op_simid': '',
                'op_red': 'CLARO',
                'fila': '1',
                'csq': '26',
                'dbm': '-61',
                'col': '1',
                'numero': '+56912345001',
                'creg': '1'
            },
            {
                'timestamp': '2025-01-15 10:00:05',
                'port': 'COM6',
                'model': 'UC20',
                'ccid': '8956030246016341462F',
                'op_simid': '',
                'op_red': 'CLARO',
                'fila': '2',
                'csq': '24',
                'dbm': '-63',
                'col': '1',
                'numero': '+56912345002',
                'creg': '1'
            },
            {
                'timestamp': '2025-01-15 10:00:10',
                'port': 'COM6',
                'model': 'UC20',
                'ccid': '8956030246016341463F',
                'op_simid': '',
                'op_red': 'MOVISTAR',
                'fila': '3',
                'csq': '28',
                'dbm': '-59',
                'col': '1',
                'numero': '+56912345003',
                'creg': '5'
            },
            # Puerto COM6 - SIM inválida (creg = 0)
            {
                'timestamp': '2025-01-15 10:00:15',
                'port': 'COM6',
                'model': 'UC20',
                'ccid': '8956030246016341464F',
                'op_simid': '',
                'op_red': '',
                'fila': '4',
                'csq': '0',
                'dbm': '-113',
                'col': '1',
                'numero': '+56912345004',
                'creg': '0'
            },
            # Puerto COM4 - 2 SIMs válidas
            {
                'timestamp': '2025-01-15 10:00:20',
                'port': 'COM4',
                'model': 'UC20',
                'ccid': '8956030246016341465F',
                'op_simid': '',
                'op_red': 'CLARO',
                'fila': '1',
                'csq': '25',
                'dbm': '-62',
                'col': '2',
                'numero': '+56922345001',
                'creg': '1'
            },
            {
                'timestamp': '2025-01-15 10:00:25',
                'port': 'COM4',
                'model': 'UC20',
                'ccid': '8956030246016341466F',
                'op_simid': '',
                'op_red': 'MOVISTAR',
                'fila': '2',
                'csq': '27',
                'dbm': '-60',
                'col': '2',
                'numero': '+56922345002',
                'creg': '1'
            },
            # Puerto COM4 - SIM inválida (numero = N/A)
            {
                'timestamp': '2025-01-15 10:00:30',
                'port': 'COM4',
                'model': 'UC20',
                'ccid': '8956030246016341467F',
                'op_simid': '',
                'op_red': '',
                'fila': '3',
                'csq': '0',
                'dbm': '-113',
                'col': '2',
                'numero': 'N/A',
                'creg': '1'
            },
            # Puerto COM3 - 1 SIM válida
            {
                'timestamp': '2025-01-15 10:00:35',
                'port': 'COM3',
                'model': 'EC25',
                'ccid': '8956030246016341468F',
                'op_simid': '',
                'op_red': 'CLARO',
                'fila': '1',
                'csq': '29',
                'dbm': '-58',
                'col': '3',
                'numero': '+56932345001',
                'creg': '1'
            }
        ]
        
        # Guardar signal_data.csv en data/
        signal_data_path = os.path.join(self.data_dir, 'signal_data.csv')
        fieldnames = ['timestamp', 'port', 'model', 'ccid', 'op_simid', 'op_red', 
                     'fila', 'csq', 'dbm', 'col', 'numero', 'creg']
        with open(signal_data_path, 'w', newline='', encoding='utf-8') as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(self.test_signal_data)
    
    def tearDown(self):
        """Limpiar ambiente de prueba."""
        os.chdir(self.original_cwd)
        shutil.rmtree(self.test_dir)
    
    def test_load_signal_data(self):
        """Test: Carga correcta de signal_data.csv."""
        manager = SlotManager()
        
        # Verificar que se cargaron todas las entradas
        self.assertEqual(len(manager.signal_data), 8)
    
    def test_filter_valid_sims(self):
        """Test: Filtrado correcto de SIMs válidas."""
        manager = SlotManager()
        
        # Verificar que solo se filtren las válidas
        # COM6: 3 válidas (4ta tiene creg=0)
        # COM4: 2 válidas (3ra tiene numero=N/A)
        # COM3: 1 válida
        # Total: 6 válidas
        
        total_valid = sum(len(slots) for slots in manager.slot_positions.values())
        self.assertEqual(total_valid, 6)
        
        # Verificar por puerto
        self.assertEqual(len(manager.slot_positions['COM6']), 3)
        self.assertEqual(len(manager.slot_positions['COM4']), 2)
        self.assertEqual(len(manager.slot_positions['COM3']), 1)
    
    def test_circular_rotation(self):
        """Test: Rotación circular funciona correctamente."""
        manager = SlotManager()
        
        # Testear rotación en COM6 (3 SIMs)
        slot1 = manager.get_next_slot('COM6')
        self.assertEqual(slot1['numero'], '+56912345001')
        self.assertEqual(slot1['fila'], '1')  # CSV strings
        
        slot2 = manager.get_next_slot('COM6')
        self.assertEqual(slot2['numero'], '+56912345002')
        self.assertEqual(slot2['fila'], '2')
        
        slot3 = manager.get_next_slot('COM6')
        self.assertEqual(slot3['numero'], '+56912345003')
        self.assertEqual(slot3['fila'], '3')
        
        # Verificar que vuelve al inicio (circular)
        slot4 = manager.get_next_slot('COM6')
        self.assertEqual(slot4['numero'], '+56912345001')
        self.assertEqual(slot4['fila'], '1')
    
    def test_state_persistence(self):
        """Test: El estado se persiste correctamente en disco."""
        # Crear primer manager y avanzar índice
        manager1 = SlotManager()
        manager1.get_next_slot('COM6')  # índice -> 1
        manager1.get_next_slot('COM6')  # índice -> 2
        
        # Verificar que slot_state.json existe en data/
        state_file = os.path.join(self.data_dir, 'slot_state.json')
        self.assertTrue(os.path.exists(state_file))
        
        # Leer estado guardado
        with open(state_file, 'r', encoding='utf-8') as f:
            state_data = json.load(f)
        
        # Verificar que el índice es 2 (después de 2 llamadas)
        self.assertEqual(state_data['indices']['COM6'], 2)
        
        # Crear nuevo manager (simula reinicio del programa)
        manager2 = SlotManager()
        
        # Verificar que el estado se cargó correctamente
        self.assertEqual(manager2.slot_indices['COM6'], 2)
        
        # El siguiente slot debe ser el tercero (índice 2)
        slot = manager2.get_current_slot('COM6')
        self.assertEqual(slot['numero'], '+56912345003')
        self.assertEqual(slot['fila'], '3')  # CSV strings
    
    def test_multiple_ports(self):
        """Test: Manejo de múltiples puertos simultáneos."""
        manager = SlotManager()
        
        # Avanzar COM6
        s1 = manager.get_next_slot('COM6')
        self.assertEqual(s1['fila'], '1')  # CSV strings
        
        # Avanzar COM4 (independiente)
        s2 = manager.get_next_slot('COM4')
        self.assertEqual(s2['fila'], '1')
        
        # Avanzar COM6 nuevamente
        s3 = manager.get_next_slot('COM6')
        self.assertEqual(s3['fila'], '2')
        
        # Verificar que los índices son independientes
        self.assertEqual(manager.slot_indices['COM6'], 2)
        self.assertEqual(manager.slot_indices['COM4'], 1)
    
    def test_reset_index(self):
        """Test: Reinicio de índices."""
        manager = SlotManager()
        
        # Avanzar el índice
        manager.get_next_slot('COM6')
        manager.get_next_slot('COM6')
        self.assertEqual(manager.slot_indices['COM6'], 2)
        
        # Reiniciar
        manager.reset_index('COM6')
        self.assertEqual(manager.slot_indices['COM6'], 0)
        
        # Verificar que se guardó en data/
        with open(os.path.join(self.data_dir, 'slot_state.json'), 'r') as f:
            state = json.load(f)
        self.assertEqual(state['indices']['COM6'], 0)
    
    def test_get_status(self):
        """Test: Obtención de estado completo."""
        manager = SlotManager()
        
        status = manager.get_status()
        
        # Verificar estructura
        self.assertIn('total_ports', status)
        self.assertIn('total_valid_sims', status)
        self.assertIn('ports', status)
        
        # Verificar valores
        self.assertEqual(status['total_ports'], 3)
        self.assertEqual(status['total_valid_sims'], 6)
        
        # Verificar info por puerto
        self.assertEqual(status['ports']['COM6']['valid_sims'], 3)
        self.assertEqual(status['ports']['COM4']['valid_sims'], 2)
        self.assertEqual(status['ports']['COM3']['valid_sims'], 1)
    
    def test_invalid_port(self):
        """Test: Manejo de puerto inválido."""
        manager = SlotManager()
        
        # Intentar obtener slot de puerto inexistente
        slot = manager.get_next_slot('COM99')
        self.assertIsNone(slot)
    
    def test_empty_signal_data(self):
        """Test: Manejo de signal_data.csv vacío."""
        # Crear signal_data.csv vacío (solo headers) en data/
        signal_data_path = os.path.join(self.data_dir, 'signal_data.csv')
        fieldnames = ['timestamp', 'port', 'model', 'ccid', 'op_simid', 'op_red', 
                     'fila', 'csq', 'dbm', 'col', 'numero', 'creg']
        with open(signal_data_path, 'w', newline='', encoding='utf-8') as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
        
        manager = SlotManager()
        
        # Verificar que no hay slots
        self.assertEqual(len(manager.slot_positions), 0)
        self.assertEqual(len(manager.get_all_ports()), 0)


def run_tests():
    """Ejecuta los tests y retorna resultado."""
    suite = unittest.TestLoader().loadTestsFromTestCase(TestSlotLogic)
    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)
    return result.wasSuccessful()


if __name__ == '__main__':
    success = run_tests()
    sys.exit(0 if success else 1)
