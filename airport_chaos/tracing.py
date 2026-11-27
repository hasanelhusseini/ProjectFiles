class Tracer:
    def __init__(self):
        self.enabled = False
        self._suspended = 0
        self.sink = print

    @property
    def active(self):
        return self.enabled and self._suspended == 0

    def log(self, message):
        if self.active:
            self.sink("  [TRACE] " + message)

    def suspend(self):
        return _Suspension(self)


class _Suspension:
    def __init__(self, tracer):
        self.tracer = tracer

    def __enter__(self):
        self.tracer._suspended += 1
        return self.tracer

    def __exit__(self, exc_type, exc, tb):
        self.tracer._suspended -= 1
        return False


tracer = Tracer()
