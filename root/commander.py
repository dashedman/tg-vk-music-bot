class Commander:
    def __init__(self):
        self._last_id = 0
        self._ids_registry = {}
    def _get_next_id(self):
        while self._last_id not in self._ids_registry:
            self._last_id = (self._last_id + 1) % 1000000
        return self._last_id
    def download_track(self, track):
        command_id = self._get_next_id()
        self._ids_registry[command_id] =
        return command_id
