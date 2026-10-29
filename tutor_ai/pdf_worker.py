"""Isolated bounded PDF metadata/text/raster extraction. No vault access."""

import io
import multiprocessing
import re
import time

from .errors import AppError, require

MAX_BYTES = 64 * 1024 * 1024
MAX_PAGES = 600


def child(connection, raw, pages, render):
    try:
        import logging
        quality_warnings = set()
        class QualityHandler(logging.Handler):
            def emit(self, record):
                quality_warnings.add("Неполное сопоставление шрифтов PDF. Проверьте текст и формулы по изображению.")
        logger = logging.getLogger("pypdf")
        logger.handlers = [QualityHandler()]
        logger.propagate = False
        # Per-process Windows memory limit. The parent also enforces wall time
        # and bounded input/output. Closing the process never touches SQLite.
        job = None
        import os
        if os.name == "nt":
            import ctypes
            from ctypes import wintypes as w
            class Basic(ctypes.Structure):
                _fields_ = [("process_time", ctypes.c_longlong), ("job_time", ctypes.c_longlong),
                            ("flags", w.DWORD), ("min_ws", ctypes.c_size_t), ("max_ws", ctypes.c_size_t),
                            ("processes", w.DWORD), ("affinity", ctypes.c_size_t), ("priority", w.DWORD), ("scheduling", w.DWORD)]
            class Io(ctypes.Structure):
                _fields_ = [(str(i), ctypes.c_ulonglong) for i in range(6)]
            class Limits(ctypes.Structure):
                _fields_ = [("basic", Basic), ("io", Io), ("process_memory", ctypes.c_size_t),
                            ("job_memory", ctypes.c_size_t), ("peak_process", ctypes.c_size_t), ("peak_job", ctypes.c_size_t)]
            kernel = ctypes.WinDLL("kernel32", use_last_error=True)
            kernel.CreateJobObjectW.restype = w.HANDLE
            kernel.SetInformationJobObject.argtypes = [w.HANDLE, ctypes.c_int, ctypes.c_void_p, w.DWORD]
            kernel.AssignProcessToJobObject.argtypes = [w.HANDLE, w.HANDLE]
            kernel.GetCurrentProcess.restype = w.HANDLE
            job = kernel.CreateJobObjectW(None, None)
            limits = Limits()
            limits.basic.flags = 0x100 | 0x2
            limits.basic.process_time = 60 * 10_000_000
            limits.process_memory = 512 * 1024 * 1024
            if not (job and kernel.SetInformationJobObject(job, 9, ctypes.byref(limits), ctypes.sizeof(limits))
                    and kernel.AssignProcessToJobObject(job, kernel.GetCurrentProcess())):
                raise RuntimeError("worker_limits")
        from pypdf import PdfReader
        reader = PdfReader(io.BytesIO(raw))
        require(not reader.is_encrypted, "PDF защищён паролем.", "source_encrypted")
        count = len(reader.pages)
        require(0 < count <= MAX_PAGES, "Источник: до 600 страниц.", "source_page_limit")
        discovered = []
        if pages is None:
            # Text-only discovery may find the end of a concatenated document,
            # not just the end of the physical PDF. Do not return whole-book text.
            for index in range(count):
                heading = (reader.pages[index].extract_text() or "")[:250]
                if re.search(r"(?im)^\s*(содержание|оглавление)\s*$", heading):
                    discovered.extend(range(index, min(index+3, count)))
        defaults = list(range(min(4, count))) + discovered[:8] + list(range(max(0, count-8), count))
        selected = sorted(set(pages if pages is not None else defaults))
        require(len(selected) <= 20 and all(isinstance(p, int) and 0 <= p < count for p in selected),
                "Выберите до 20 существующих PDF-страниц.", "source_pages")
        result = {"pages": count, "selected": [], "metadata": str(reader.metadata or {})[:4000]}
        total = 0
        for index in selected:
            value = reader.pages[index].extract_text() or ""
            total += len(value)
            require(len(value) <= 30000 and total <= 120000, "Слишком много текста. Выберите меньше страниц.", "source_fragment_limit")
            result["selected"].append({"pdf_page": index+1, "text": value})
        if render:
            require(len(selected) <= 4, "Растер: до 4 страниц за партию.")
            from PySide6.QtCore import QCoreApplication, QBuffer, QIODevice, QSize
            from PySide6.QtPdf import QPdfDocument
            app = QCoreApplication.instance() or QCoreApplication([])
            buffer = QBuffer()
            buffer.setData(raw)
            buffer.open(QIODevice.OpenModeFlag.ReadOnly)
            doc = QPdfDocument(None)
            doc.load(buffer)
            for item in result["selected"]:
                image = doc.render(item["pdf_page"]-1, QSize(1200, 1600))
                require(not image.isNull() and image.width()*image.height() <= 25_000_000,
                        "Не удалось безопасно отрисовать страницу.", "source_render")
                output = QBuffer()
                output.open(QIODevice.OpenModeFlag.WriteOnly)
                image.save(output, "PNG")
                data = bytes(output.data())
                require(len(data) <= 8*1024*1024, "Растр слишком велик.", "source_render_limit")
                item["image"] = data
            doc.close()
            del app
        result["warnings"] = sorted(quality_warnings)
        connection.send((True, result))
    except Exception as exc:
        connection.send((False, exc.code if isinstance(exc, AppError) else "source_parse"))
    finally:
        connection.close()


def inspect(raw, pages=None, render=False, cancel=None, timeout=60):
    require(isinstance(raw, bytes) and 0 < len(raw) <= MAX_BYTES, "Источник: до 64 МиБ.", "source_size")
    context = multiprocessing.get_context("spawn")
    parent, sender = context.Pipe(duplex=False)
    process = context.Process(target=child, args=(sender, raw, pages, render), daemon=True)
    process.start()
    sender.close()
    started = time.monotonic()
    try:
        while not parent.poll(0.05):
            require(not cancel or not cancel.is_set(), "Разбор отменён.", "cancelled")
            require(time.monotonic()-started < timeout, "Истекло время разбора PDF.", "source_worker_timeout")
            require(process.is_alive(), "Процесс разбора остановлен (лимит ресурсов или повреждённый PDF).", "source_worker_failed")
        ok, result = parent.recv()
        require(ok, "Не удалось обработать выбранные страницы PDF: " + str(result), str(result) if not ok else "validation")
        return result
    except EOFError as exc:
        raise AppError("Процесс разбора завершился без результата.", "source_worker_failed") from exc
    finally:
        parent.close()
        process.join(timeout=1)
        if process.is_alive():
            process.terminate()
            process.join(timeout=3)
