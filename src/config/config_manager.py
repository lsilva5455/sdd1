"""
ConfigManager - Gestión de configuración del sistema.
Carga config.json desde el directorio raíz del proyecto.
Si no existe, lo crea con valores por defecto.
"""
import json
import os


class ConfigManager:
    """Gestiona la carga y acceso a la configuración del sistema."""
    
    DEFAULT_CONFIG = {
        "filas": 16,
        "baudrate": 115200,
        "at_timeout": 3,
        "cambio_fila_minutos": 5,
        "output_identities": "~\\Documents\\sadmin_ext\\numeros\\lista_sim_actual.txt",
        "simclient_exec_path": "~\\AppData\\Local\\SimClient\\SimClient.exe",
        "simbanks": [
            {
                "control_port": "COM19",
                "modems": [
                    {"port": "COM6", "col": "01"}, {"port": "COM4", "col": "02"},
                    {"port": "COM3", "col": "03"}, {"port": "COM5", "col": "04"},
                    {"port": "COM7", "col": "05"}, {"port": "COM8", "col": "06"},
                    {"port": "COM10", "col": "07"}, {"port": "COM9", "col": "08"}
                ]
            },
            {
                "control_port": "COM20",
                "modems": [
                    {"port": "COM11", "col": "01"}, {"port": "COM12", "col": "02"},
                    {"port": "COM13", "col": "03"}, {"port": "COM14", "col": "04"},
                    {"port": "COM15", "col": "05"}, {"port": "COM16", "col": "06"},
                    {"port": "COM18", "col": "07"}, {"port": "COM17", "col": "08"}
                ]
            }
        ]
    }
    
    def __init__(self, config_file_path=None):
        """
        Inicializa el ConfigManager.
        
        Args:
            config_file_path: Ruta al config.json. Si es None, busca en os.getcwd()
        """
        if config_file_path is None:
            config_file_path = os.path.join(os.getcwd(), 'config.json')
        
        self.config_file_path = config_file_path
        self.config_data = self.load_config()

    def load_config(self):
        """
        Carga config.json. Si no existe, lo crea con valores por defecto.
        
        Returns:
            Diccionario con la configuración
        """
        if not os.path.exists(self.config_file_path):
            print(f"⚠️  config.json no encontrado en: {self.config_file_path}")
            print("📝 Creando config.json con configuración por defecto...")
            
            try:
                # Crear directorio si no existe
                os.makedirs(os.path.dirname(self.config_file_path), exist_ok=True)
                
                # Escribir config por defecto
                with open(self.config_file_path, 'w', encoding='utf-8') as f:
                    json.dump(self.DEFAULT_CONFIG, f, indent=2, ensure_ascii=False)
                
                print(f"✅ config.json creado exitosamente")
                return self.DEFAULT_CONFIG.copy()
                
            except Exception as e:
                print(f"❌ Error al crear config.json: {e}")
                raise
        
        # Cargar archivo existente
        try:
            with open(self.config_file_path, 'r', encoding='utf-8') as config_file:
                return json.load(config_file)
        except json.JSONDecodeError as e:
            print(f"❌ Error: config.json tiene formato JSON inválido: {e}")
            raise
        except Exception as e:
            print(f"❌ Error al leer config.json: {e}")
            raise

    def get_path(self, key):
        """
        Obtiene una ruta de la configuración, expandiendo ~ si es necesario.
        
        Args:
            key: Clave en config.json que contiene una ruta
            
        Returns:
            Ruta expandida (con ~ reemplazado por la ruta del usuario)
        """
        path = self.config_data.get(key)
        if path and isinstance(path, str) and path.startswith('~'):
            return os.path.expanduser(path)
        return path
    
    def get(self, key, default=None):
        """
        Obtiene un valor de la configuración.
        
        Args:
            key: Clave a buscar
            default: Valor por defecto si no existe
            
        Returns:
            Valor de la configuración o default
        """
        return self.config_data.get(key, default)