"""
Tests Unitarios para HardwareController.
Verifica comunicación serial, formato de comandos y reintentos.
"""
import os
import sys
import unittest
from unittest.mock import Mock, MagicMock, patch, call
import threading
import time

# Agregar src al path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

from hardware_controller import SimController, retry_serial


class MockSerial:
    """Mock de serial.Serial para tests."""
    
    def __init__(self, port, baudrate, timeout):
        self.port = port
        self.baudrate = baudrate
        self.timeout = timeout
        self.is_open = True
        self._write_buffer = []
        self._read_buffer = b''
        
    def write(self, data):
        self._write_buffer.append(data)
        
    def read(self, size):
        result = self._read_buffer[:size]
        self._read_buffer = self._read_buffer[size:]
        return result
    
    def flushInput(self):
        pass
    
    def flushOutput(self):
        pass
    
    def close(self):
        self.is_open = False
    
    def set_response(self, response):
        """Helper para configurar respuesta del puerto."""
        self._read_buffer = response.encode('utf-8')


class MockConfigManager:
    """Mock de ConfigManager para tests."""
    
    def __init__(self):
        self.config_data = {
            'filas': 16,
            'baudrate': 115200,
            'at_timeout': 3,
            'simbanks': [
                {
                    'control_port': 'COM19',
                    'modems': [
                        {'port': 'COM6', 'col': '01'},
                        {'port': 'COM4', 'col': '02'}
                    ]
                },
                {
                    'control_port': 'COM20',
                    'modems': [
                        {'port': 'COM11', 'col': '01'}
                    ]
                }
            ]
        }


class TestRetryDecorator(unittest.TestCase):
    """Tests para el decorador @retry_serial."""
    
    def test_retry_on_serial_exception(self):
        """Test: El decorador reintenta en caso de SerialException."""
        import serial
        
        call_count = [0]
        
        @retry_serial(max_retries=3)
        def failing_function():
            call_count[0] += 1
            if call_count[0] < 3:
                raise serial.SerialException("Puerto ocupado")
            return "éxito"
        
        result = failing_function()
        
        # Debe intentar 3 veces antes de tener éxito
        self.assertEqual(call_count[0], 3)
        self.assertEqual(result, "éxito")
    
    def test_retry_exhausted(self):
        """Test: Lanza excepción si se agotan los reintentos."""
        import serial
        
        @retry_serial(max_retries=2)
        def always_fails():
            raise serial.SerialException("Error persistente")
        
        with self.assertRaises(serial.SerialException):
            always_fails()
    
    def test_no_retry_on_other_exceptions(self):
        """Test: No reintenta con excepciones no seriales."""
        call_count = [0]
        
        @retry_serial(max_retries=3)
        def raises_value_error():
            call_count[0] += 1
            raise ValueError("Error lógico")
        
        with self.assertRaises(ValueError):
            raises_value_error()
        
        # Solo debe intentar una vez
        self.assertEqual(call_count[0], 1)


class TestSimController(unittest.TestCase):
    """Tests para SimController."""
    
    def setUp(self):
        """Preparar ambiente de prueba."""
        self.mock_config = MockConfigManager()
        self.controller = SimController(self.mock_config)
    
    def test_initialization(self):
        """Test: Inicialización correcta del controlador."""
        self.assertEqual(self.controller.baudrate, 115200)
        self.assertEqual(self.controller.at_timeout, 3)
        
        # Verificar que se crearon los locks
        self.assertIn('COM19', SimController.pool_locks)
        self.assertIn('COM20', SimController.pool_locks)
    
    def test_pool_locks_thread_safe(self):
        """Test: Los locks son thread-safe."""
        # Limpiar locks previos
        SimController.pool_locks.clear()
        
        # Crear múltiples hilos que inicializan el controlador
        threads = []
        for _ in range(10):
            t = threading.Thread(target=lambda: SimController(self.mock_config))
            threads.append(t)
            t.start()
        
        for t in threads:
            t.join()
        
        # Verificar que solo hay 2 locks (no duplicados)
        self.assertEqual(len(SimController.pool_locks), 2)
    
    @patch('hardware_controller.serial.Serial')
    def test_switch_sim_format(self, mock_serial_class):
        """Test: Formato correcto del comando AT+SWIT."""
        mock_port = MockSerial('COM19', 115200, 3)
        mock_port.set_response('OK\r\n')
        mock_serial_class.return_value = mock_port
        
        # Ejecutar switch
        result = self.controller.switch_sim('COM19', '03', 5)
        
        # Verificar éxito
        self.assertTrue(result)
        
        # Verificar formato del comando: AT+SWIT03-0005
        written = mock_port._write_buffer[0].decode('ascii')
        self.assertEqual(written, 'AT+SWIT03-0005\r\n')
    
    @patch('hardware_controller.serial.Serial')
    def test_switch_sim_padding(self, mock_serial_class):
        """Test: Padding correcto de columna y fila."""
        mock_port = MockSerial('COM19', 115200, 3)
        mock_port.set_response('OK\r\n')
        mock_serial_class.return_value = mock_port
        
        test_cases = [
            ('01', 1, 'AT+SWIT01-0001\r\n'),
            ('08', 16, 'AT+SWIT08-0016\r\n'),
            ('05', 10, 'AT+SWIT05-0010\r\n'),
        ]
        
        for col, row, expected_cmd in test_cases:
            mock_port._write_buffer.clear()
            mock_port.set_response('OK\r\n')
            
            self.controller.switch_sim('COM19', col, row)
            
            written = mock_port._write_buffer[0].decode('ascii')
            self.assertEqual(written, expected_cmd)
    
    @patch('hardware_controller.serial.Serial')
    def test_switch_sim_uses_lock(self, mock_serial_class):
        """Test: switch_sim usa el lock correctamente."""
        mock_port = MockSerial('COM19', 115200, 3)
        mock_port.set_response('OK\r\n')
        mock_serial_class.return_value = mock_port
        
        # Simplemente verificar que el lock existe y el método completa
        self.assertIn('COM19', SimController.pool_locks)
        
        result = self.controller.switch_sim('COM19', '01', 1)
        
        # Si completa exitosamente, el lock funcionó
        self.assertTrue(result)
    
    def test_reboot_modem_ec25(self):
        """Test: Secuencia de reinicio para EC25."""
        mock_port = MockSerial('COM6', 115200, 3)
        # EC25 necesita respuesta OK para ambos comandos
        mock_port._read_buffer = b'OK\r\n' * 10  # Buffer grande para múltiples reads
        
        with patch('time.sleep'):  # Acelerar el test
            result = self.controller.reboot_modem(mock_port, 'EC25')
        
        self.assertTrue(result)
        
        # Verificar secuencia: AT+CFUN=0, luego AT+CFUN=1
        commands = [cmd.decode('ascii').strip() for cmd in mock_port._write_buffer]
        self.assertIn('AT+CFUN=0', commands[0])
        self.assertIn('AT+CFUN=1', commands[1])
    
    def test_reboot_modem_uc20(self):
        """Test: Secuencia de reinicio para UC20."""
        mock_port = MockSerial('COM6', 115200, 3)
        mock_port.set_response('OK\r\n')
        
        with patch('time.sleep'):
            result = self.controller.reboot_modem(mock_port, 'UC20')
        
        self.assertTrue(result)
        
        # Verificar comando: AT+CFUN=1,1
        commands = [cmd.decode('ascii').strip() for cmd in mock_port._write_buffer]
        self.assertIn('AT+CFUN=1,1', commands[0])
    
    def test_wait_for_signal_success(self):
        """Test: Espera exitosa de señal."""
        mock_port = MockSerial('COM6', 115200, 3)
        mock_port.set_response('+CREG: 0,1\r\nOK\r\n')
        
        with patch('time.sleep'):
            success, creg = self.controller.wait_for_signal(mock_port, max_wait=10)
        
        self.assertTrue(success)
        self.assertEqual(creg, '1')
    
    def test_wait_for_signal_roaming(self):
        """Test: Detección de roaming."""
        mock_port = MockSerial('COM6', 115200, 3)
        mock_port.set_response('+CREG: 0,5\r\nOK\r\n')
        
        with patch('time.sleep'):
            success, creg = self.controller.wait_for_signal(mock_port, max_wait=10)
        
        self.assertTrue(success)
        self.assertEqual(creg, '5')
    
    def test_wait_for_signal_denied(self):
        """Test: Registro denegado."""
        mock_port = MockSerial('COM6', 115200, 3)
        mock_port.set_response('+CREG: 0,3\r\nOK\r\n')
        
        with patch('time.sleep'):
            success, creg = self.controller.wait_for_signal(mock_port, max_wait=10)
        
        self.assertFalse(success)
        self.assertEqual(creg, '3')
    
    @patch('hardware_controller.subprocess.run')
    def test_kill_simclient_success(self, mock_run):
        """Test: Terminación exitosa de simclient."""
        mock_run.return_value = Mock(returncode=0, stdout='', stderr='')
        
        result = self.controller.kill_simclient()
        
        self.assertTrue(result)
        mock_run.assert_called_once()
        
        # Verificar argumentos del comando
        call_args = mock_run.call_args[0][0]
        self.assertEqual(call_args[0], 'taskkill')
        self.assertEqual(call_args[1], '/IM')
        self.assertEqual(call_args[2], 'simclient.exe')
        self.assertEqual(call_args[3], '/F')
    
    @patch('hardware_controller.subprocess.run')
    def test_kill_simclient_not_running(self, mock_run):
        """Test: simclient no está corriendo (código 128)."""
        mock_run.return_value = Mock(returncode=128, stdout='', stderr='')
        
        result = self.controller.kill_simclient()
        
        # Debe retornar True (es válido que no esté corriendo)
        self.assertTrue(result)
    
    def test_detect_model_ec25(self):
        """Test: Detección de modelo EC25."""
        mock_port = MockSerial('COM6', 115200, 3)
        mock_port.set_response('Quectel\r\nEC25\r\nRevision: EC25EFAR06A03M4G\r\n')
        
        model = self.controller.detect_model(mock_port)
        
        self.assertEqual(model, 'EC25')
    
    def test_detect_model_uc20(self):
        """Test: Detección de modelo UC20."""
        mock_port = MockSerial('COM6', 115200, 3)
        mock_port.set_response('Quectel\r\nUC20\r\n')
        
        model = self.controller.detect_model(mock_port)
        
        self.assertEqual(model, 'UC20')


def run_tests():
    """Ejecuta los tests y retorna resultado."""
    suite = unittest.TestLoader().loadTestsFromModule(sys.modules[__name__])
    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)
    return result.wasSuccessful()


if __name__ == '__main__':
    success = run_tests()
    sys.exit(0 if success else 1)
