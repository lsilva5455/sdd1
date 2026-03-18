"""
STUB / SCAFFOLD — Not used in production.

This module is a placeholder for a future refactoring of the logging system.
Production logging uses src/logger_config.py which provides RotatingFileHandler
with colorama support, log cleanup, and system info logging.

Production code: src/logger_config.py
"""

import logging
import os


class Logger:
    def __init__(self, name, log_file="app.log", level=logging.INFO):
        self.logger = logging.getLogger(name)
        self.logger.setLevel(level)

        # Create file handler
        file_handler = logging.FileHandler(log_file)
        file_handler.setLevel(level)

        # Create console handler
        console_handler = logging.StreamHandler()
        console_handler.setLevel(level)

        # Create formatter
        formatter = logging.Formatter(
            "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
        )
        file_handler.setFormatter(formatter)
        console_handler.setFormatter(formatter)

        # Add handlers to the logger
        self.logger.addHandler(file_handler)
        self.logger.addHandler(console_handler)

    def debug(self, message):
        self.logger.debug(message)

    def info(self, message):
        self.logger.info(message)

    def warning(self, message):
        self.logger.warning(message)

    def error(self, message):
        self.logger.error(message)

    def critical(self, message):
        self.logger.critical(message)


# Example usage
if __name__ == "__main__":
    log = Logger(__name__)
    log.info("Logger initialized")
