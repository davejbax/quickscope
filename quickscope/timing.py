import time
from threading import Timer

class PreciseTimer:
    # TODO doc

    delay = 0 # Delay in seconds
    callback = None # Callback function
    started = None

    def __init__(self, delay, callback):
        self.delay = delay
        self.callback = callback

    def start(self):
        if self.started is not None:
            raise RuntimeError("Timer already started.")
        
        self.started = time.perf_counter()

        # Use bulk timer if delay is greater than 6s; we start
        # the precise timer 5s before-hand.
        if self.delay > 6:
            timer = Timer(self.delay - 5, self._start_precisely)
            timer.start()
        else:
            self._start_precisely()

    def _start_precisely(self):
        now       = time.perf_counter()
        elapsed   = now - self.started
        remaining = self.delay - elapsed

        if remaining <= 0:
            self.callback()
            return

        while True:
            if (time.perf_counter() - now) >= remaining:
                break

        self.callback()
