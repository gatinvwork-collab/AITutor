"""Bounded serialized native commands; background accounting never piles up."""
import threading
import time
from concurrent.futures import ThreadPoolExecutor

from .errors import AppError


class NativeWorker:
    def __init__(self, limit=16, observe=None):
        self.executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="native-command")
        self.lock = threading.Lock()
        self.pending = 0
        self.closed = False
        self.limit = limit
        self.observe = observe or (lambda **_: None)

    def _submit(self, function, args, label, idle):
        queued = time.perf_counter()
        with self.lock:
            if idle and (self.closed or self.pending):
                return None
            if self.closed or self.pending >= self.limit:
                raise AppError("Приложение занято. Дождитесь текущей операции и повторите действие.", "busy")
            self.pending += 1
        def run():
            started = time.perf_counter()
            try:
                return function(*args)
            finally:
                self.observe(command=label, wait_ms=(started - queued) * 1000,
                             duration_ms=(time.perf_counter() - started) * 1000)
        def finished(_):
            with self.lock:
                self.pending -= 1
        try:
            future = self.executor.submit(run)
        except Exception:
            finished(None)
            raise
        future.add_done_callback(finished)
        return future

    def submit(self, function, *args, label="unknown"):
        return self._submit(function, args, label, False)

    def submit_idle(self, function):
        return self._submit(function, (), "tick", True)

    def shutdown(self, **kwargs):
        with self.lock:
            self.closed = True
        self.executor.shutdown(**kwargs)
