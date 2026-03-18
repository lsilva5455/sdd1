"""
SlotLogic - Lógica de Negocio con Persistencia de Estado.
Gestiona la rotación circular de SIMs con estado persistente en disco.
Soporta recarga dinámica de lista_pos.json para actualización en tiempo real.
"""
import json
import csv
import os
from typing import Dict, List, Optional
from datetime import datetime


class SlotManager:
    """
    Gestiona la lógica de rotación de slots con persistencia en disco.
    El estado sobrevive a reinicios del programa.
    Soporta recarga dinámica de lista_pos.json.
    """
    
    def __init__(self, data_manager=None, signal_data_path=None):
        """
        Inicializa el SlotManager.
        
        Args:
            data_manager: Instancia de DataManager (opcional)
            signal_data_path: Ruta al signal_data.csv (opcional)
        """
        self.data_manager = data_manager
        
        # Crear directorio data/ si no existe
        data_dir = os.path.join(os.getcwd(), 'data')
        os.makedirs(data_dir, exist_ok=True)
        
        self.state_file = os.path.join(data_dir, 'slot_state.json')
        self.lista_pos_file = os.path.join(data_dir, 'lista_pos.json')
        
        # Cargar signal_data
        if signal_data_path is None:
            signal_data_path = os.path.join(data_dir, 'signal_data.csv')
        
        self.signal_data = self._load_signal_data(signal_data_path)
        
        # Generar posiciones válidas por puerto
        self.slot_positions = self.generate_slot_pos(self.signal_data)
        
        # Cargar o inicializar estado de índices
        self.slot_indices = self._load_state()
        
        # Inicializar índices para puertos nuevos
        for port in self.slot_positions.keys():
            if port not in self.slot_indices:
                self.slot_indices[port] = 0
        
        # Guardar estado inicial
        self._save_state()
        
        # Timestamp de última modificación de lista_pos.json
        self._lista_pos_mtime = 0
        if os.path.exists(self.lista_pos_file):
            self._lista_pos_mtime = os.path.getmtime(self.lista_pos_file)
    
    def _load_signal_data(self, path: str) -> List[Dict]:
        """
        Carga signal_data.csv.
        
        Args:
            path: Ruta al archivo signal_data.csv
            
        Returns:
            Lista de datos de señal
        """
        if not os.path.exists(path):
            print(f"⚠️  signal_data.csv no encontrado en: {path}")
            return []
        
        try:
            data = []
            with open(path, 'r', encoding='utf-8') as f:
                reader = csv.DictReader(f)
                for row in reader:
                    data.append(dict(row))
            print(f"✅ Cargado signal_data.csv: {len(data)} entradas")
            return data
        except Exception as e:
            print(f"❌ Error al cargar signal_data.csv: {e}")
            return []
    
    def _load_state(self) -> Dict[str, int]:
        """
        Carga el estado de índices desde slot_state.json.
        Si no existe, retorna diccionario vacío.
        
        Returns:
            Diccionario {port: índice_actual}
        """
        if not os.path.exists(self.state_file):
            print(f"📝 slot_state.json no existe, creando estado nuevo...")
            return {}
        
        try:
            with open(self.state_file, 'r', encoding='utf-8') as f:
                state = json.load(f)
            
            # Extraer los índices (puede venir con estructura o solo los índices)
            if 'indices' in state:
                indices = state['indices']
            else:
                indices = state
            
            print(f"✅ Estado cargado desde slot_state.json: {len(indices)} puertos")
            return indices
        except Exception as e:
            print(f"⚠️  Error al cargar slot_state.json: {e}, iniciando nuevo estado")
            return {}
    
    def _save_state(self):
        """
        Guarda el estado actual en slot_state.json.
        CRÍTICO: Se llama después de cada cambio para persistencia en tiempo real.
        """
        try:
            state_data = {
                'last_update': datetime.now().isoformat(),
                'indices': self.slot_indices
            }
            
            with open(self.state_file, 'w', encoding='utf-8') as f:
                json.dump(state_data, f, indent=2, ensure_ascii=False)
            
            # Log para debugging
            print(f"💾 slot_state.json actualizado: {len(self.slot_indices)} puertos")
            
            # Duplicar si data_manager está disponible
            if self.data_manager:
                self.data_manager._mirror_data_files()
            
        except Exception as e:
            print(f"❌ Error al guardar slot_state.json: {e}")
            import traceback
            traceback.print_exc()
    
    def generate_slot_pos(self, signal_data: List[Dict]) -> Dict[str, List[Dict]]:
        """
        Genera posiciones válidas de slots agrupadas por puerto.
        
        Criterios de validez (MISMOS que numero_simid.txt):
        - numero NO es None, NO es 'N/A', NO está vacío
        - numero cumple formato válido por país (_validar_numero_por_pais)
        - numero NO está duplicado (singularidad phone/simid)
        - ccid NO es None, NO es 'N/A'
        - creg es '1' (Home) o '5' (Roaming)
        
        Args:
            signal_data: Lista de datos de señal
            
        Returns:
            Diccionario {port: [lista_ordenada_de_slots_válidos]}
        """
        # Filtrar SIMs válidas CON MISMOS CRITERIOS que numero_simid.txt
        valid_sims = []
        seen_numeros = set()  # Para detectar duplicados
        invalid_format_count = 0
        duplicate_count = 0
        invalid_ccid_count = 0
        invalid_creg_count = 0
        
        for sim in signal_data:
            numero = sim.get('numero')
            ccid = sim.get('ccid')
            creg = str(sim.get('creg', ''))
            
            # Filtro 1: Validar número básico
            if numero is None or numero == 'N/A' or numero == '':
                continue
            
            # Filtro 2: Validar CCID básico
            if ccid is None or ccid == 'N/A' or ccid == '':
                invalid_ccid_count += 1
                continue
            
            # Filtro 3: Validar registro en red (creg = 1 o 5)
            if creg not in ['1', '5']:
                invalid_creg_count += 1
                continue
            
            # Filtro 4: Validar formato de número por país (MISMA FUNCIÓN que numero_simid.txt)
            if self.data_manager and not self.data_manager._validar_numero_por_pais(numero, ccid):
                invalid_format_count += 1
                continue
            
            # Filtro 5: Verificar duplicados (singularidad phone/simid)
            if numero in seen_numeros:
                duplicate_count += 1
                continue
            
            seen_numeros.add(numero)
            valid_sims.append(sim)
        
        # Mostrar estadísticas de filtrado
        print(f"🔍 SIMs válidas encontradas: {len(valid_sims)}/{len(signal_data)}")
        if invalid_format_count > 0:
            print(f"   ⚠️  Rechazadas por formato inválido: {invalid_format_count}")
        if duplicate_count > 0:
            print(f"   ⚠️  Rechazadas por duplicados: {duplicate_count}")
        if invalid_ccid_count > 0:
            print(f"   ⚠️  Rechazadas por CCID inválido: {invalid_ccid_count}")
        if invalid_creg_count > 0:
            print(f"   ⚠️  Rechazadas por CREG inválido: {invalid_creg_count}")
        
        # Agrupar por puerto
        port_groups = {}
        for sim in valid_sims:
            port = sim.get('port')
            if not port:
                continue
            
            if port not in port_groups:
                port_groups[port] = []
            
            port_groups[port].append(sim)
        
        # Ordenar cada grupo por columna física
        for port in port_groups:
            port_groups[port].sort(key=lambda x: int(x.get('col', '0')))
        
        # Mostrar resumen
        for port, sims in sorted(port_groups.items()):
            print(f"  📍 {port}: {len(sims)} SIMs válidas")
        
        return port_groups
    
    def reload_lista_pos(self):
        """
        Recarga lista_pos.json si ha sido modificado.
        Ajusta índices si el tamaño de alguna lista cambió.
        """
        if not os.path.exists(self.lista_pos_file):
            return
        
        # Verificar si el archivo fue modificado
        current_mtime = os.path.getmtime(self.lista_pos_file)
        if current_mtime == self._lista_pos_mtime:
            return  # No ha cambiado
        
        try:
            # Cargar nueva lista_pos.json
            with open(self.lista_pos_file, 'r', encoding='utf-8') as f:
                new_positions = json.load(f)
            
            print(f"🔄 Recargando lista_pos.json (modificado)")
            
            # Actualizar slot_positions y ajustar índices
            for port, new_slots in new_positions.items():
                old_count = len(self.slot_positions.get(port, []))
                new_count = len(new_slots)
                
                # Actualizar posiciones
                self.slot_positions[port] = new_slots
                
                # Ajustar índice si está fuera de rango
                current_index = self.slot_indices.get(port, 0)
                if current_index >= new_count and new_count > 0:
                    self.slot_indices[port] = 0
                    print(f"  ⚠️  {port}: índice {current_index} → 0 (lista reducida de {old_count} a {new_count})")
                elif new_count == 0:
                    self.slot_indices[port] = 0
                    print(f"  ⚠️  {port}: sin slots válidos")
            
            # Actualizar timestamp
            self._lista_pos_mtime = current_mtime
            
            # Guardar estado actualizado
            self._save_state()
            
        except Exception as e:
            print(f"❌ Error al recargar lista_pos.json: {e}")
    
    def get_next_slot(self, port: str) -> Optional[Dict]:
        """
        Obtiene el siguiente slot válido para un puerto (rotación circular).
        
        CRÍTICO: 
        - Recarga lista_pos.json si fue modificado
        - Guarda el estado inmediatamente después de avanzar el índice
        
        Args:
            port: Puerto COM (ej: 'COM6')
            
        Returns:
            Diccionario con datos del slot o None si no hay slots válidos
        """
        # Recargar lista_pos.json si cambió
        self.reload_lista_pos()
        
        # Verificar que el puerto existe
        if port not in self.slot_positions:
            print(f"⚠️  Puerto {port} no tiene slots válidos")
            return None
        
        # Obtener lista de slots para este puerto
        slots = self.slot_positions[port]
        
        if not slots:
            print(f"⚠️  Puerto {port} no tiene slots disponibles")
            return None
        
        # Obtener índice actual (con protección por si está fuera de rango)
        current_index = self.slot_indices.get(port, 0)
        
        # Protección: si el índice está fuera de rango, reiniciar a 0
        if current_index >= len(slots):
            current_index = 0
            self.slot_indices[port] = 0
        
        # Avanzar al siguiente (circular)
        next_index = (current_index + 1) % len(slots)
        
        # IMPORTANTE: Obtener el slot del SIGUIENTE índice
        next_slot = slots[next_index]
        
        # Actualizar índice a la siguiente posición
        self.slot_indices[port] = next_index
        
        # LOG DETALLADO: Mostrar transición
        print(f"🔄 {port}: Índice {current_index} → {next_index} (total: {len(slots)} slots)")
        print(f"   📍 Slot seleccionado: Fila {next_slot.get('fila')}, Col {next_slot.get('col')}, Phone {next_slot.get('numero', 'N/A')}, CCID {next_slot.get('ccid', 'N/A')}")
        
        # PERSISTENCIA EN TIEMPO REAL: Guardar estado inmediatamente
        self._save_state()
        
        return next_slot
    
    def get_current_slot(self, port: str) -> Optional[Dict]:
        """
        Obtiene el slot actual sin avanzar el índice.
        
        Args:
            port: Puerto COM
            
        Returns:
            Diccionario con datos del slot actual o None
        """
        if port not in self.slot_positions:
            return None
        
        slots = self.slot_positions[port]
        if not slots:
            return None
        
        current_index = self.slot_indices.get(port, 0)
        
        if current_index >= len(slots):
            current_index = 0
            self.slot_indices[port] = current_index
        
        return slots[current_index]
    
    def get_slot_count(self, port: str) -> int:
        """
        Retorna el número de slots válidos para un puerto.
        
        Args:
            port: Puerto COM
            
        Returns:
            Cantidad de slots válidos
        """
        if port not in self.slot_positions:
            return 0
        return len(self.slot_positions[port])
    
    def get_all_ports(self) -> List[str]:
        """
        Retorna lista de todos los puertos con slots válidos.
        
        Returns:
            Lista de puertos COM ordenados
        """
        return sorted(self.slot_positions.keys())
    
    def reset_index(self, port: str):
        """
        Reinicia el índice de un puerto a 0.
        
        Args:
            port: Puerto COM a reiniciar
        """
        if port in self.slot_indices:
            self.slot_indices[port] = 0
            self._save_state()
            print(f"🔄 Índice de {port} reiniciado a 0")
    
    def reset_all_indices(self):
        """
        Reinicia todos los índices a 0.
        """
        for port in self.slot_indices:
            self.slot_indices[port] = 0
        self._save_state()
        print("🔄 Todos los índices reiniciados a 0")
    
    def get_status(self) -> Dict:
        """
        Obtiene el estado completo del SlotManager.
        
        Returns:
            Diccionario con información de estado
        """
        status = {
            'total_ports': len(self.slot_positions),
            'total_valid_sims': sum(len(slots) for slots in self.slot_positions.values()),
            'state_file': self.state_file,
            'state_exists': os.path.exists(self.state_file),
            'ports': {}
        }
        
        for port in sorted(self.slot_positions.keys()):
            status['ports'][port] = {
                'valid_sims': len(self.slot_positions[port]),
                'current_index': self.slot_indices.get(port, 0)
            }
        
        return status
    
    def get_unregistered_slots_for_port(self, port: str) -> List[Dict]:
        """
        Obtiene filas que tienen número pero NO están registradas en la red.
        Estas son candidatas para intentar registro en slots vacíos.
        
        Args:
            port: Puerto COM a buscar
            
        Returns:
            Lista de slots con numero pero creg != 1 y 5, ordenadas por columna
        """
        unregistered = []
        
        for sim in self.signal_data:
            sim_port = sim.get('port')
            if sim_port != port:
                continue
            
            numero = sim.get('numero')
            ccid = sim.get('ccid')
            creg = str(sim.get('creg', ''))
            
            # Debe tener número válido
            if numero is None or numero == 'N/A' or numero == '':
                continue
            
            # Debe tener CCID válido
            if ccid is None or ccid == 'N/A' or ccid == '':
                continue
            
            # NO debe estar registrada (creg diferente de 1 o 5)
            if creg in ['1', '5']:
                continue
            
            unregistered.append(sim)
        
        # Ordenar por columna física
        unregistered.sort(key=lambda x: int(x.get('col', '0')))
        
        return unregistered
    
    def get_empty_ports(self) -> List[str]:
        """
        Obtiene lista de puertos que NO tienen slots válidos (lista_pos vacía).
        Estos puertos están en signal_data pero no tienen SIMs registradas.
        
        Returns:
            Lista de puertos COM sin slots válidos
        """
        # Obtener todos los puertos en signal_data
        all_ports_in_signal = set()
        for sim in self.signal_data:
            port = sim.get('port')
            if port:
                all_ports_in_signal.add(port)
        
        # Filtrar solo los que NO tienen lista_pos
        empty_ports = []
        for port in sorted(all_ports_in_signal):
            if port not in self.slot_positions or len(self.slot_positions[port]) == 0:
                empty_ports.append(port)
        
        return empty_ports
    
    def add_port_to_production(self, port: str, valid_slots: List[Dict]):
        """
        Gradúa un puerto empty a producción después de mapeo completo.
        Actualiza slot_positions, slot_indices, lista_pos.json y slot_state.json.
        
        Args:
            port: Puerto COM a agregar
            valid_slots: Lista de slots que se registraron exitosamente
        """
        print(f"🎓 Graduando {port} a producción con {len(valid_slots)} SIMs registradas")
        
        # 1. Actualizar slot_positions en memoria
        self.slot_positions[port] = valid_slots
        
        # 2. Inicializar índice en 0
        self.slot_indices[port] = 0
        
        # 3. Guardar estado actualizado
        self._save_state()
        
        # 4. Actualizar lista_pos.json en disco
        self._update_lista_pos_file()
        
        print(f"✅ {port} ahora en producción normal")
        for i, slot in enumerate(valid_slots):
            print(f"   [{i}] Fila {slot.get('fila')}, Col {slot.get('col')}, Phone {slot.get('numero')}")
    
    def _update_lista_pos_file(self):
        """
        Actualiza el archivo lista_pos.json con el estado actual de slot_positions.
        """
        try:
            with open(self.lista_pos_file, 'w', encoding='utf-8') as f:
                json.dump(self.slot_positions, f, indent=2, ensure_ascii=False)
            print(f"💾 lista_pos.json actualizado: {len(self.slot_positions)} puertos")
        except Exception as e:
            print(f"❌ Error actualizando lista_pos.json: {e}")
