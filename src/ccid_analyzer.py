"""
Analizador automático de desajustes de CCID.
Busca el CCID real en signal_data.csv y determina la causa del error.
"""
import csv
import os
from typing import Dict, List, Optional, Tuple


class CCIDAnalyzer:
    """Analiza desajustes de CCID y determina patrones y causas."""
    
    def __init__(self, data_dir: str = None):
        self.data_dir = data_dir or os.path.join(os.getcwd(), 'data')
        self.signal_data_path = os.path.join(self.data_dir, 'signal_data.csv')
        self._signal_data_cache = None
    
    def _load_signal_data(self) -> List[Dict]:
        """Carga signal_data.csv una sola vez (cache)."""
        if self._signal_data_cache is not None:
            return self._signal_data_cache
        
        if not os.path.exists(self.signal_data_path):
            return []
        
        data = []
        try:
            with open(self.signal_data_path, 'r', encoding='utf-8') as f:
                reader = csv.DictReader(f)
                for row in reader:
                    data.append(dict(row))
            self._signal_data_cache = data
        except Exception:
            pass
        
        return data
    
    def find_ccid_location(self, ccid: str) -> List[Dict]:
        """
        Busca un CCID en signal_data.csv y retorna todas sus ubicaciones.
        
        Returns:
            Lista de diccionarios con: port, fila, col, numero, creg
        """
        signal_data = self._load_signal_data()
        locations = []
        
        for row in signal_data:
            if row.get('ccid') == ccid:
                locations.append({
                    'port': row.get('port'),
                    'fila': row.get('fila'),
                    'col': row.get('col'),
                    'numero': row.get('numero', 'N/A'),
                    'creg': row.get('creg', '0'),
                    'timestamp': row.get('timestamp', '')
                })
        
        return locations
    
    def analyze_mismatch(self, port: str, expected_fila: str, expected_col: str, 
                        expected_ccid: str, actual_ccid: str) -> Dict:
        """
        Analiza un desajuste de CCID y determina la causa probable.
        
        Args:
            port: Puerto COM donde ocurrió el error
            expected_fila: Fila esperada
            expected_col: Columna esperada
            expected_ccid: CCID que se esperaba leer
            actual_ccid: CCID que realmente se leyó
        
        Returns:
            Diccionario con diagnóstico completo
        """
        result = {
            'port': port,
            'expected_location': f"Fila {expected_fila}, Col {expected_col}",
            'expected_ccid': expected_ccid,
            'actual_ccid': actual_ccid,
            'actual_locations': [],
            'diagnosis': '',
            'cause': '',
            'action': ''
        }
        
        # Buscar el CCID real en signal_data
        actual_locations = self.find_ccid_location(actual_ccid)
        result['actual_locations'] = actual_locations
        
        if not actual_locations:
            result['diagnosis'] = "CCID no encontrado en signal_data.csv"
            result['cause'] = "El SIM físicamente conectado no fue escaneado o tiene un CCID diferente"
            result['action'] = "Ejecutar --scan para actualizar signal_data.csv"
            return result
        
        # Analizar la ubicación real vs esperada
        same_port_locations = [loc for loc in actual_locations if loc['port'] == port]
        
        if not same_port_locations:
            # El CCID está en otro puerto
            other_ports = [loc['port'] for loc in actual_locations]
            result['diagnosis'] = f"CCID encontrado en otro(s) puerto(s): {', '.join(other_ports)}"
            result['cause'] = "Cable mal conectado - El puerto está conectado a un slot incorrecto"
            result['action'] = f"Verificar conexión física del cable entre SimBank y {port}"
            return result
        
        # El CCID está en el mismo puerto, pero diferente fila
        actual_loc = same_port_locations[0]
        actual_fila = actual_loc['fila']
        actual_col = actual_loc['col']
        
        if actual_col != expected_col:
            result['diagnosis'] = f"Columna incorrecta - Esperada: {expected_col}, Real: {actual_col}"
            result['cause'] = "Cable conectado a columna incorrecta en el SimBank"
            result['action'] = f"Verificar que {port} esté conectado a Col {expected_col}, no Col {actual_col}"
            return result
        
        # Misma columna, diferente fila
        fila_diff = int(actual_fila) - int(expected_fila)
        result['diagnosis'] = f"Fila incorrecta - Esperada: {expected_fila}, Real: {actual_fila} (diferencia: {fila_diff:+d})"
        
        # Determinar patrón de error
        if actual_fila == "1":
            result['cause'] = "Modem leyendo Fila 1 (posición inicial) - TIMING INSUFICIENTE"
            result['action'] = "El switch no completó antes de leer CCID. Aumentar delay después de AT+SWIT"
        elif abs(fila_diff) == 1:
            result['cause'] = f"Leyendo fila adyacente ({fila_diff:+d}) - Switch parcialmente completado"
            result['action'] = "Aumentar delay de estabilización después de switch"
        else:
            result['cause'] = f"Leyendo Fila {actual_fila} en lugar de {expected_fila} - Switch incompleto"
            result['action'] = "Problema de timing en SimBank o comando AT+SWIT no esperó completar"
        
        # Agregar información del SIM real
        if actual_loc['numero'] != 'N/A':
            result['actual_sim_info'] = f"Número: {actual_loc['numero']}, CREG: {actual_loc['creg']}"
        else:
            result['actual_sim_info'] = f"Sin número, CREG: {actual_loc['creg']}"
        
        return result
    
    def get_suggested_delay(self, error_pattern: List[Dict]) -> int:
        """
        Analiza múltiples errores y sugiere un delay apropiado.
        
        Args:
            error_pattern: Lista de resultados de analyze_mismatch()
        
        Returns:
            Delay sugerido en segundos
        """
        # Analizar patrones comunes
        fila_1_errors = sum(1 for err in error_pattern 
                           if err.get('actual_locations') and 
                           any(loc['fila'] == '1' for loc in err['actual_locations']))
        
        if fila_1_errors > len(error_pattern) * 0.5:
            # Más del 50% leyendo fila 1 = switch no está ejecutándose
            return 15  # Aumentar a 15s
        elif fila_1_errors > 0:
            # Algunos leyendo fila 1 = delay insuficiente
            return 12  # Aumentar a 12s
        else:
            # Lecturas de filas aleatorias = problema de hardware
            return 10  # Mantener 10s pero investigar hardware
    
    def format_diagnosis(self, analysis: Dict) -> List[str]:
        """
        Formatea el diagnóstico para logging.
        
        Returns:
            Lista de strings para logging
        """
        lines = []
        lines.append(f"🔍 ANÁLISIS AUTOMÁTICO DE CCID:")
        lines.append(f"   Puerto: {analysis['port']}")
        lines.append(f"   Ubicación esperada: {analysis['expected_location']}")
        
        if analysis['actual_locations']:
            loc = analysis['actual_locations'][0]
            lines.append(f"   Ubicación real: Fila {loc['fila']}, Col {loc['col']}")
            if 'actual_sim_info' in analysis:
                lines.append(f"   SIM real: {analysis['actual_sim_info']}")
        else:
            lines.append(f"   Ubicación real: NO ENCONTRADO en signal_data.csv")
        
        lines.append(f"")
        lines.append(f"   📋 Diagnóstico: {analysis['diagnosis']}")
        lines.append(f"   🔍 Causa probable: {analysis['cause']}")
        lines.append(f"   🔧 Acción: {analysis['action']}")
        
        return lines
