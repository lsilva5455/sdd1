"""
STUB / SCAFFOLD — Not used in production.

This module is a placeholder for a future refactoring of the modem control
logic currently implemented in src/hardware_controller.py (SimController class).
Once refactored, this will handle individual modem AT command interactions
(CSQ, CREG, CFUN, CCID, model detection) as a dedicated class.

Production code: src/hardware_controller.py
"""


class ModemController:
    def __init__(self, serial_manager):
        self.serial_manager = serial_manager

    def send_at_command(self, command):
        response = self.serial_manager.send_command(command)
        return response

    def reset_modem(self):
        self.send_at_command("AT+CFUN=1,1")

    def check_signal_quality(self):
        response = self.send_at_command("AT+CSQ")
        return self.parse_signal_quality(response)

    def parse_signal_quality(self, response):
        if response.startswith("+CSQ:"):
            parts = response.split(":")[1].strip().split(",")
            rssi = int(parts[0])
            ber = int(parts[1])
            return {"rssi": rssi, "ber": ber}
        return None

    def initialize_modem(self):
        self.reset_modem()
        self.send_at_command("AT+CREG?")
        self.send_at_command("AT+CGREG?")
