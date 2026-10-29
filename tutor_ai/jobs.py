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
        self.publication_errors = set()

    def submit(self, identity, run, publish):
        if not self.slots.acquire(blocking=False):
            raise AppError("Очередь сетевых задач заполнена. Повторите позже.", "busy")
        event = threading.Event()
        with self.lock:
            self.cancelled[identity] = event

        def work():
            try:
                result, error = None, None
                try:
                    if event.is_set():
                        raise AppError("Задача отменена.", "cancelled")
                    result = run(event)
                except Exception as exc:
                    error = exc.code if isinstance(exc, AppError) else "technical_error"
                try:
                    publish(result, error, event.is_set())
                except Exception:
                    # A failed durable publication is not a second worker result.
                    # Keep the last valid vault; login reconciles interrupted jobs.
                    with self.lock:
                        self.publication_errors.add(identity)
                        if len(self.publication_errors) > 100:
                            self.publication_errors.pop()
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

    def cancel_one(self, identity):
        with self.lock:
            event = self.cancelled.get(identity)
            if event:
                event.set()
            return event is not None

    def is_cancel_requested(self, identity):
        with self.lock:
            event = self.cancelled.get(identity)
            return bool(event and event.is_set())

    def shutdown(self):
        self.cancel()
        self.pool.shutdown(wait=False, cancel_futures=False)
