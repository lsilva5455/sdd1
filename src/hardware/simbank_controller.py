"""
STUB / SCAFFOLD — Not used in production.

This module is a placeholder for a future refactoring of SimBank control logic.
Production SimBank commands (AT+CWSIM, AT+NEXT00, AT+SWIT) are handled by
the SimController class in src/hardware_controller.py, which manages both
SimBank control ports and modem ports with concurrency locks.

Production code: src/hardware_controller.py
"""


class SimBankController:
    def __init__(self, control_port):
        self.control_port = control_port

    def switch_sim(self, column, row):
        command = f"AT+SWIT{column}-{row:04d}"
        self.send_command(command)

    def send_command(self, command):
        # TODO: Implement serial communication via control port
        pass

    def reset_slot(self, slot_port):
        # TODO: Implement slot reset logic
        pass

    def get_status(self):
        # TODO: Implement SimBank status query
        pass
