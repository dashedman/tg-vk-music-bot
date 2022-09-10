from typing import Callable


class TemporaryBlock:
    def __init__(self, on_timeout: Callable, data):
        self.on_timeout = on_timeout
        self.data = data

    def start(self):
        pass