"""Bounded network work; workers never access SQLite or mutable service state."""

import threading
from concurrent.futures import ThreadPoolExecutor

from .errors import AppError


class NetworkJobs:
    def __init__(self):
        self.pool = ThreadPoolExecutor(max_workers=2, thread_name_prefix="tutor-network")
        self.slots = threading.BoundedSemaphore(8)
        self.lock = threading.Lock()
        self.cancelled = {}

    def submit(self, identity, run, publish):
        if not self.slots.acquire(blocking=False):
            raise AppError("Очередь сетевых задач заполнена. Повторите позже.", "busy")
        event = threading.Event()
        with self.lock:
            self.cancelled[identity] = event

        def work():
            try:
                if event.is_set():
                    raise AppError("Задача отменена.", "cancelled")
                result = run(event)
                publish(result, None, event.is_set())
            except Exception as exc:
                publish(None, exc.code if isinstance(exc, AppError) else "technical_error", event.is_set())
            finally:
                with self.lock:
                    self.cancelled.pop(identity, None)
                self.slots.release()

        try:
            self.pool.submit(work)
        except Exception:
            with self.lock:
                self.cancelled.pop(identity, None)
            self.slots.release()
            raise

    def cancel(self):
        with self.lock:
            for event in self.cancelled.values():
                event.set()

    def shutdown(self):
        self.cancel()
        self.pool.shutdown(wait=False, cancel_futures=False)
