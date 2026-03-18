Al iniciar el programa necesito que se genere un icono usando * como pixeles. Luego de eso un mensaje en varios colores indicando datos del programa, capacidad, hora, etc.

## Resolved Questions

1. **Icon shape**: Signal bars (cellular signal strength icon)
2. **Data fields**: Program name, version, date/time, SimBanks count, modem count, IP address, Flask port, platform/OS, Node (e.g., N99)
3. **Data source**: Dynamic from `config.json`, with "N/A" fallback
4. **Color library**: `colorama`
5. **Version string**: Create new `__version__ = "1.0.0"` constant