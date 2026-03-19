1.-
Si bien, los mencionados son los mas usados. Este lo llamaremos grupo1(el mas relevante) y tendremos otros 2 grupo. siendo el grupo 2 los comandos que encuentres que se usaron el los scripts (mas los que te voy a mencionar mas abajo) y el grupo3 el restante de todos los comandos EC25-UC20 indexados segun manual.
El grupo 2 tambien va a quedar visible en hardware-control y el grupo3 debe quedar referenciado a un.md donde esten todos los otros comandos que esten bien indexados para un correcto funcionamiento del sdd. Sin son demasiados comandos debes seleccionar los mas importante.

AT-commandos grupos 2.
Te voy a entregar prompt/parrafos que no debes ejecutar ni tomar en cuenta solo extraer los comandos AT.

". Inicialización y Diagnóstico
ATI: Identifica el fabricante, modelo (EC25 vs UC20) y versión de firmware.
AT+CMEE=2: Habilita el reporte de errores extendidos en formato de texto (en lugar de códigos numéricos) para facilitar el debug.
AT+CPIN?: Verifica si la tarjeta SIM está presente y si requiere código PIN.
AT+CSQ: Mide la calidad de la señal recibida (RSSI) y la tasa de error de bit (BER).
AT+CREG?: Consulta el estado del registro en la red celular (Home, Roaming o No Registrado).
AT+COPS?: Identifica el operador al cual está conectado el módulo (ej: "WOM").
2. Configuración de Capa de Red y Voz
AT+QCFG="ims",1: Activa las capacidades de servicios multimedia (VoLTE) en el firmware de Quectel.
AT+QAUDMOD=1: Selecciona el canal de audio (analógico o digital) para asegurar que el IVR escuche los tonos.
AT+QCFG="nwscanmode",2,1: Fuerza al módulo a entrar en modo WCDMA (3G) exclusivamente, ignorando LTE. El "1" aplica el cambio de inmediato.
AT+QCFG="nwscanmode",0,1: Restaura el modo de escaneo automático (LTE, 3G y 2G).
3. Gestión de SMS (Mensajería)
AT+CMGF=1: Configura el módulo en Modo Texto para que los SMS sean legibles directamente (en lugar del formato hexadecimal PDU).
AT+CMGD=1,4: Borra todos los mensajes de la memoria de la SIM (mensajes leídos, no leídos, enviados y borradores) para asegurar una bandeja limpia.
AT+CMGL="ALL": Lista todos los mensajes almacenados en la memoria activa para su procesamiento.
4. Control de Llamada y Señalización (DTMF)
ATD103;: Inicia una llamada de voz al número 103. El punto y coma (;) es crítico; sin él, el comando se interpreta como una llamada de datos (CSD) y fallará en redes modernas.
AT+CLCC: Lista las llamadas actuales. Se usa para detectar el estado 0 (Active), que confirma que la llamada fue contestada y el audio está fluyendo.
AT+VTS="X": Envía un tono DTMF (Dual-Tone Multi-Frequency) del carácter "X". Es el comando que simula la pulsación de teclas durante la llamada.
ATH: Cuelga todas las llamadas activas (Hang up).
AT+CEER: Consulta el código de error extendido de la última llamada fallida (causa de liberación), esencial para diagnosticar rechazos de red como el código 258.
Observación Técnica sobre el "Fondo del Problema":
Si el link no llega al primer intento pese a que la digitación es correcta, es posible que el SMS se esté quedando en el SMS Service Center (SMSC) de WOM mientras el módulo re-escanea de 3G a LTE.
Para solucionar esto de fondo sin reintentar la llamada, se podría probar manteniendo el módulo en 3G fijo durante toda la fase de espera del SMS, ya que el cambio de bandas (nwscanmode 2 -> 0) provoca un desprendimiento de red (detach) que puede retrasar la entrega de mensajes entrantes."

"AT+CPBW=1,"",129,"reinicio"


APN
AT+QICSGP=1,2,"wap.tmovil.cl","wap","wap",0
PROBAR CON 
AT+QICSGP=1,1,"wap.tmovil.cl","wap","wap",1 

RED
AT+COPS?
en qu red esta

SIGNAL
AT+CSQ
https://m2msupport.neAT+t/m2msupport/atcsq-signal-quality/


at+creg?
proporciona información sobre el estado del registro y
https://m2msupport.net/m2msupport/atcreg-network-registration/



APAGAR Y ENCEDER ANTENA RF (REINICIO)
EC25
AT+CFUN=0
AT+CFUN=1

PHONEBOOK 
Leer:
AT+CPBR=1,2
AT+CPBR=1
escribir:
AT+CPBW=1,"56959312964",129,"myphone"
SMS
https://www.developershome.com/sms/cmgdCommand.asp
https://m2msupport.net/m2msupport/sms-at-commands/


LEER SMS
AT+CMGF=1 
1=SMS MODE - 0=PDU MODE
DEFECTO=0
AT+CMGL="ALL"
lee todo
lee solo los recibiod no leidos
https://stackoverflow.com/questions/3182554/receiving-sms-using-at-commands

BORRAR SMS
AT+CMGD=1
borra el index 1
AT+CMGD=[,1]
borra todos los mensaje  recibidos y leidos
AT+CMGD=[,4]
borra todo

ENVIAR SMS
** Directo
AT+CMGS="6863"
Respuesta def1: AT+CMGS="6863"
>
numero^Z y presionar ctrl-z
Respuesta def1: numero
+CMGS: 2

OK

+CMTI: "ME",1

** guardarlo de memoria y despues enviarlo
AT+CMGW="6863"
>
numero^Z y presionar ctrl-z

Si se guarda en el index 0 el mensaje se envia con:
AT+CMSS=0



POOL


AT+SWIT02-0001
la columna 2 va a la fila 1
AT+SWIT00-0005
todas las columnas van a la posicion5

USSD
enviar 
AT+CUSD=1,"*888#",15
AT+CUSD=1,"*103#",15

Recibir ussd
AT+QURCCFG="urcport","uart1"
Conocer config actual
AT+QURCCFG="urcport"

"
referencia:
### Modem Commands

| Command | Purpose | Target |
|---------|---------|--------|
| `AT+CCID` | Get ICCID of the active SIM | Modem port |
| `AT+CREG?` | Query cellular network registration status | Modem port |
| `AT+CSQ` | Get signal level (RSSI) | Modem port |
| `AT+CFUN=0` / `AT+CFUN=1` | EC25 modem reboot (radio off → on) | Modem port |
| `AT+CFUN=1,1` | UC20 modem reboot (full reset) | Modem port |
| `ATI` / `AT+CGMM` | Identify modem model | Modem port |