"""
STUB / SCAFFOLD — Not used in production.

This module is a placeholder for a future refactoring of serial port management.
Production serial communication is handled inline within src/hardware_controller.py
(SimController class) using pyserial directly with the retry_serial decorator.

Production code: src/hardware_controller.py
"""

from serial import Serial, SerialException
import time


class SerialManager:
    def __init__(self, port, baudrate=115200, timeout=1):
        self.port = port
        self.baudrate = baudrate
        self.timeout = timeout
        self.serial_connection = None

    def open(self):
        if self.serial_connection is None:
            try:
                self.serial_connection = Serial(
                    self.port, self.baudrate, timeout=self.timeout
                )
            except SerialException as e:
                raise Exception(f"Failed to open serial port {self.port}: {e}")

    def close(self):
        if self.serial_connection is not None:
            self.serial_connection.close()
            self.serial_connection = None

    def is_open(self):
        return self.serial_connection is not None and self.serial_connection.is_open

    def write(self, data):
        if not self.is_open():
            raise Exception("Serial port is not open")
        self.serial_connection.write(data)

    def read(self, size=1):
        if not self.is_open():
            raise Exception("Serial port is not open")
        return self.serial_connection.read(size)

    def flush(self):
        if self.is_open():
            self.serial_connection.flush()

    def __del__(self):
        self.close()
