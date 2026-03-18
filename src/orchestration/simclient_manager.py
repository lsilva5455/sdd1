"""
STUB / SCAFFOLD — Not used in production.

This module is a placeholder for a future refactoring of the SimClient lifecycle
management. Production SimClient launch/kill logic is handled within the
Orchestrator class in src/main.py and the kill_simclient() function in
src/hardware_controller.py (SimController).

Production code: src/main.py (Orchestrator), src/hardware_controller.py (SimController)
"""


class SimClientManager:
    def __init__(self, config_manager=None):
        self.config = config_manager

    def initialize(self):
        # TODO: Implement SimClient initialization
        pass

    def start_workflow(self):
        # TODO: Implement main workflow logic
        pass

    def shutdown(self):
        # TODO: Implement SimClient shutdown (kill process)
        pass
