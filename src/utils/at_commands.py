"""
STUB / SCAFFOLD — Not used in production.

This module is a placeholder for centralizing AT command string definitions.
Production AT commands are currently defined inline within src/hardware_controller.py
(SimController class): AT+CWSIM, AT+NEXT00, AT+SWIT, AT+CCID, AT+CREG, AT+CSQ,
AT+CFUN, ATI, AT+CGMM.

Production code: src/hardware_controller.py
"""


class ATCommands:
    """Class to define AT commands for modem communication."""

    @staticmethod
    def reset():
        """AT command to reset the modem."""
        return "AT+CFUN=1,1"

    @staticmethod
    def check_signal_quality():
        """AT command to check signal quality."""
        return "AT+CSQ"

    @staticmethod
    def set_network_mode(mode):
        """AT command to set the network mode.

        Args:
            mode (str): The network mode to set (e.g., '3G', '4G').
        """
        return f"AT+CNMP={mode}"

    @staticmethod
    def send_sms(phone_number, message):
        """AT command to send an SMS.

        Args:
            phone_number (str): The recipient's phone number.
            message (str): The message to send.
        """
        return f'AT+CMGS="{phone_number}"\n{message}\x1a'

    @staticmethod
    def read_sms(index):
        """AT command to read an SMS from storage.

        Args:
            index (int): The index of the SMS to read.
        """
        return f"AT+CMGR={index}"

    @staticmethod
    def delete_sms(index):
        """AT command to delete an SMS from storage.

        Args:
            index (int): The index of the SMS to delete.
        """
        return f"AT+CMGD={index}"
