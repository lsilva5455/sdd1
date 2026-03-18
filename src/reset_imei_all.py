# -*- coding: utf-8 -*-
#!/usr/bin/env python
log=True
import random
from sys import path as syspath
from os import path as ospath
from termcolor import cprint
HOME = ospath.expanduser('~')
syspath.append(f'{HOME}/sadmin')
syspath.append(f'{HOME}/sadmin/src')
import serial
import time
help_menu='''
help

Poner simid con ultimos 2 digitos correspondan al slot ej.  
    * slot1 => simid xxxxxxx.....01
    * slot12 => simid xxxxxx.....12


'''
import sys
import glob
import serial
import colorama
colorama.init()
def luhn_residue(digits):
    """ Lunh10 residue value """
    s = sum(d if (n % 2 == 1) else (0, 2, 4, 6, 8, 1, 3, 5, 7, 9)[d]
            for n, d in enumerate(map(int, reversed(digits))))
    return (10 - s % 10) % 10
def imei_generate():
    prefix = ''.join(str(random.randrange(0, 9)) for _ in range(14))  # Generate 14 random digits
    check_digit = luhn_residue(prefix)
    imei = f"{prefix}{-check_digit % 10}"  # Append the check digit
    return imei

def is_number(string0):
    isnum=True
    try:
        int(string0)
    except:
        isnum=False
    return isnum
def is_simid(string0):
    is_simid=False
    simid = string0.replace("AT+QCCID","").replace("OK","").replace("\\r","").replace("\\n","").replace("F","").replace("f","").replace("OK", '').strip().replace("+CREG: 2", '').replace("+CREG: 3", '').replace("ERROR", '').replace("RDY", '').replace("+CFUN: 1", '').replace("+CPIN: READY", '').replace("Call Ready", '').replace("AT+QCCID", "").replace("+QCCID:", "").replace("+CME : 13",'').replace("+QUSIM: 1",'').replace("+QIND: SMS DONE",'').replace("+QIND: PB DONE",'').strip()####################falta e v3
    if len(simid) in [19,20]  and is_number(simid):
        is_simid=True
    return is_simid,simid
def serial_ports():
    """ Lists serial port names

        :raises EnvironmentError:
            On unsupported or unknown platforms
        :returns:
            A list of the serial ports available on the system
    """
    if sys.platform.startswith('win'):
        ports = ['COM%s' % (i + 1) for i in range(256)]
    elif sys.platform.startswith('linux') or sys.platform.startswith('cygwin'):
        # this excludes your current terminal "/dev/tty"
        ports = glob.glob('/dev/tty[A-Za-z]*')
    elif sys.platform.startswith('darwin'):
        ports = glob.glob('/dev/tty.*')
    else:
        raise EnvironmentError('Unsupported platform')

    result = []
    for port in ports:
        try:
            s = serial.Serial(port)
            s.close()
            result.append(port)
        except (OSError, serial.SerialException):
            pass
    return result
def docom(datos):
    comdatos=[]
    for dato in datos:
        comdatos.append(f'COM{dato[1]}')
    return comdatos
# def luhn_residue(digits):
#     return sum(sum(divmod(int(d) * (1 + i % 2), 10)) for i, d in enumerate(digits[::-1])) % 10
# def generate_var2():
#     prefix = ''.join(str(random.randrange(0, 9)) for _ in range(14))  # Generate 14 random digits
#     check_digit = luhn_residue(prefix)
#     imei = f"{prefix}{-check_digit % 10}"  # Append the check digit
#     return imei
prefix1=['35281219','35743593','86920307','35000921','86509406','35020450',
          '35050556','35195483','35532662','35562311','35031569','35172510',
          '35277252','35277252','35799425','35069390' ,'35261071' ,'35033626']
# prefix1=['35532662','35562311','35031569','35172510']
def generate_var2():
    prefix2 = ''.join(str(random.randrange(0, 9)) for _ in range(6))  # Generate 14 random digits
    prefix=random.choice(prefix1)+prefix2
    check_digit = luhn_residue(prefix)
    imei = f"{prefix}{check_digit}"  # Append the check digit
    return imei
import setup
RP_POOL_1=setup.RP_POOL_1
MAX_NUM_NODOS=setup.MAX_NUM_NODOS
MODEM_TOTAL=setup.MODEM_TOTAL
MODEM_INICIAL=setup.MODEM_INICIAL
def main(log=False):
    cprint('Comenzado pre-inicio','cyan')
    pools= []
    for pool_port in range(RP_POOL_1,RP_POOL_1+MAX_NUM_NODOS):
        pools.append(pool_port)
    if log:cprint(f"Pool declarados en setup RP_POOL_1:{RP_POOL_1} - MAX_NUM_NODOS: {MAX_NUM_NODOS} {pools}",'cyan')
    nodo=1
    DICT_NODO={}
    pool_port_nodo=pools[nodo-1]
    reintentar=True
    while reintentar:
        reintentar=False
        DICT_NODO_INI=DICT_NODO
        # datos_ini=datos
        for com in serial_ports():
            try:
                if log:cprint(f'reset_imei_all - main > Puerto: {com}','cyan')
                ser = serial.Serial(com, 115200, timeout=0)
                time.sleep(0.1)
                ser.write("AT+GSN\r".encode())
                time.sleep(0.1)
                response = ser.read(200)
                var1=response.decode().replace("AT+GSN","").replace("OK","").replace("\\r","").replace("\\n","").replace("F","").replace("f","").strip()
                if log:cprint(f'puerto:{com} - Iniciando reinicio - {var1}','yellow')
                var2_=generate_var2()
                if log:cprint(f'puerto:{com} - intentando escribir nuevo registro: {var2_}','white')
                ser.write(f'AT+EGMR=1,7,"{var2_}"\r'.encode())
                time.sleep(0.2)
                response = ser.read(200)
                ser.write("AT+GSN\r".encode())
                time.sleep(0.25)
                response = ser.read(200)
                var2=response.decode().replace("AT+GSN","").replace("OK","").replace("\\r","").replace("\\n","").replace("F","").replace("f","").strip()
                if var1 == var2:
                    if log:cprint(f'puerto:{com} - var1:{var1} - var2:{var2} Reinicio NO LOGRADO','magenta')
                    print
                else:
                    if log:cprint(f'puerto:{com} - Reinicio LOGRADO','green')
            except Exception as error:
                cprint(f'Error en {com}, reiniciar slot, revisar si led esta parpadeando','red')
                cprint(error,'red')
                pass
            finally:
                try:
                    ser.flush()
                    ser.close()
                except:
                    pass    
            time.sleep(0.01)

        modem_flag=True
        
    cprint('Pre-inicio Finalizado','green')

if __name__ == "__main__":
    try:
        main(log=log)
        print("\n" + "="*60)
        cprint('PROCESO COMPLETADO EXITOSAMENTE', 'green')
        print("="*60)
    except Exception as e:
        print("\n" + "="*60)
        cprint(f'ERROR EN EJECUCION: {e}', 'red')
        print("="*60)
        import traceback
        traceback.print_exc()
    finally:
        # Lanzar Iniciar_mps.bat en paralelo antes de esperar
        import subprocess
        import os
        repo_dir = ospath.join(HOME, 'mp_core', 'mp_simclient')
        iniciar_script = ospath.join(repo_dir, 'Iniciar_mps.bat')
        if ospath.exists(iniciar_script):
            print("\n" + "="*60)
            cprint('Iniciando Iniciar_mps.bat...', 'cyan')
            print("="*60)
            subprocess.Popen(['cmd', '/c', 'start', 'cmd', '/c', iniciar_script], cwd=repo_dir)
        
        input("\nPresione ENTER para cerrar esta ventana...")
