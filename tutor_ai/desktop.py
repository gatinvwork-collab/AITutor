"""Qt WebView host: fixed bridge, local resources and native file selection."""

import json
import os
import sys
from pathlib import Path

from .errors import AppError
from .service import Service
from .transfer import Transfer, installation_lock
from .worker import NativeWorker
from .diagnostics import Diagnostics


def portable_root():
    return Path(sys.executable).resolve().parent if getattr(sys, "frozen", False) else Path(__file__).resolve().parent.parent


def run(smoke=False, root_override=None, service_factory=Service, test_hook=None, diagnostics=False):
    from PySide6.QtCore import QObject, QTimer, QUrl, Signal, Slot, QLockFile
    from PySide6.QtWidgets import QApplication, QFileDialog, QMainWindow, QMessageBox
    from PySide6.QtWebChannel import QWebChannel
    from PySide6.QtWebEngineCore import QWebEnginePage, QWebEngineProfile, QWebEngineUrlRequestInterceptor
    from PySide6.QtWebEngineWidgets import QWebEngineView

    root = Path(root_override).resolve() if root_override else portable_root()
    data = root / "app-data"
    # Qt/Chromium-managed data stays in the portable directory, set before QApplication.
    os.environ["QTWEBENGINE_DICTIONARIES_PATH"] = str(data / "cache" / "dictionaries")
    app = QApplication(sys.argv[:1])
    app.setApplicationName("Tutor-AI")
    app.setOrganizationName("Tutor-AI")
    try:
        data.mkdir(parents=True, exist_ok=True)
        instance_lock = QLockFile(str(data / "instance.lock"))
        if not instance_lock.tryLock(0):
            QMessageBox.warning(None, "ИИ-репетитор", "Эта папка данных уже открыта другим экземпляром приложения.")
            return 1
        service = service_factory(data)
        probe = data / "cache" / ".write-check"
        probe.write_bytes(b"ok")
        probe.unlink()
    except OSError:
        QMessageBox.critical(None, "ИИ-репетитор", "Нет доступа к записи рядом с приложением. "
                             "Перенесите папку в доступный для записи каталог.")
        return 1
    ui = Path(getattr(sys, "_MEIPASS", portable_root())) / "ui"
    from PySide6.QtGui import QIcon
    icon = QIcon(str(ui / "assets" / "Tutor-AI.ico"))
    app.setWindowIcon(icon)
    timings = Diagnostics(data, diagnostics, Service.COMMANDS)
    pool = NativeWorker(observe=timings.command)
    transfer = Transfer(root, sys.executable if getattr(sys, "frozen", False) else None)
    transferred_executable = None
    recovery_data = None

    class LocalOnly(QWebEngineUrlRequestInterceptor):
        def interceptRequest(self, info):
            url = info.requestUrl()
            if url.scheme() in ("qrc", "data", "about"):
                return
            if url.isLocalFile():
                resolved = Path(url.toLocalFile()).resolve()
                if resolved.is_relative_to(ui.resolve()):
                    return
            info.block(True)

    class Page(QWebEnginePage):
        def acceptNavigationRequest(self, url, navigation_type, main_frame):
            return url.scheme() == "about" or (url.isLocalFile() and Path(url.toLocalFile()).resolve()
                                               == (ui / "index.html").resolve())

        def createWindow(self, _):
            return None

        def javaScriptConsoleMessage(self, *_):
            # JS console may contain entered data. Never mirror it to technical logs.
            pass

    class Bridge(QObject):
        response = Signal(str, str)
        checkpointFailed = Signal(bool)

        def submit(self, rid, function, *args, label="unknown"):
            try:
                pool.submit(function, rid, *args, label=label)
            except (AppError, RuntimeError):
                self.response.emit(rid, json.dumps({"error": "Приложение занято. Дождитесь текущей операции.",
                                                   "code": "busy"}))

        @Slot(str, str, str)
        def request(self, rid, command, payload):
            nonlocal recovery_data
            if len(payload) > 200_000 or len(rid) > 100:
                self.response.emit(rid, json.dumps({"error": "Запрос слишком велик."}))
                return
            if command == "cancel_request":
                transfer.cancel()
                result = service.cancel_request()
                self.response.emit(rid, json.dumps({"result": result}))
            elif command == "choose_transfer":
                try:
                    if service.actor or service.store.exists:
                        raise AppError("Перенос доступен до регистрации в пустой установке. Выберите отдельную папку.")
                    source = QFileDialog.getExistingDirectory(window, "Корень прежней установки (с app-data)")
                    if not source:
                        self.response.emit(rid, json.dumps({"result": None}))
                        return
                    destination = root
                    if json.loads(payload).get("separate"):
                        selected = QFileDialog.getExistingDirectory(window, "Пустая папка новой установки Tutor-AI")
                        if not selected:
                            self.response.emit(rid, json.dumps({"result": None}))
                            return
                        destination = Path(selected)
                    self.submit(rid, self.transfer_prepare, source, destination, label="choose_transfer")
                except AppError as exc:
                    self.response.emit(rid, json.dumps({"error": str(exc)}, ensure_ascii=False))
            elif command == "choose_transfer_recovery":
                if service.actor:
                    self.response.emit(rid, json.dumps({"error": "Сначала выйдите из профиля."}))
                    return
                selected = QFileDialog.getExistingDirectory(window, "Новая установка с незавершённым переносом")
                if not selected:
                    self.response.emit(rid, json.dumps({"result": None}))
                    return
                recovery_data = Path(selected) / "app-data"
                self.submit(rid, self.transfer_execute, "recover_transfer", "{}", label="recover_transfer")
            elif command in ("run_transfer", "recover_transfer", "launch_transferred"):
                self.submit(rid, self.transfer_execute, command, payload, label=command)
            elif command == "export_trace":
                try:
                    result = service.developer("view", **json.loads(payload))
                    path, _ = QFileDialog.getSaveFileName(window, "Экспорт содержит персональные учебные данные", "learning-trace.json", "JSON (*.json)")
                    if path:
                        from .crypto import atomic_write
                        atomic_write(Path(path), json.dumps(result, ensure_ascii=False, indent=2).encode())
                    self.response.emit(rid, json.dumps({"result": {"exported": bool(path)}}))
                except (AppError, OSError):
                    self.response.emit(rid, json.dumps({"error": "Не удалось экспортировать разрешённые диагностические записи."}, ensure_ascii=False))
            elif command == "pick_source":
                try:
                    import time
                    import secrets
                    args = json.loads(payload)
                    service.access(args.get("student"))
                    path, _ = QFileDialog.getOpenFileName(window, "Выбрать источник книги/УМК (до 64 МиБ)", "", "PDF (*.pdf)")
                    result = None
                    if path:
                        from .pdf_worker import MAX_BYTES
                        from .errors import require
                        require(Path(path).stat().st_size <= MAX_BYTES, "Источник: до 64 МиБ.", "source_size")
                        with open(path, "rb") as stream:
                            raw = stream.read(MAX_BYTES+1)
                        require(len(raw) <= MAX_BYTES, "Источник слишком велик.", "source_size")
                        token = secrets.token_urlsafe(24)
                        service.source_handles.clear()
                        service.source_handles[token] = {"bytes": raw, "context": service.context,
                            "student": args["student"], "created": time.monotonic()}
                        result = {"handle": token, "name": Path(path).name, "bytes": len(raw)}
                    self.response.emit(rid, json.dumps({"result": result}, ensure_ascii=False))
                except (AppError, OSError) as exc:
                    self.response.emit(rid, json.dumps({"error": str(exc) if isinstance(exc, AppError) else "Не удалось прочитать источник."}, ensure_ascii=False))
            elif command == "pick_file":
                if not service.actor:
                    self.response.emit(rid, json.dumps({"error": "Сначала войдите."}))
                    return
                path, _ = QFileDialog.getOpenFileName(window, "Выбрать задание", "",
                    "Учебные материалы (*.txt *.py *.csv *.pdf *.docx *.png *.jpg *.jpeg *.webp)")
                if not path:
                    self.response.emit(rid, json.dumps({"result": None}))
                    return
                self.submit(rid, self.import_selected, path, label="pick_file")
            elif command == "speak":
                try:
                    service.user()
                    text = json.loads(payload).get("text", "")
                    from PySide6.QtTextToSpeech import QTextToSpeech
                    if not hasattr(self, "speech"):
                        self.speech = QTextToSpeech(self)
                    if not self.speech.availableVoices():
                        raise AppError("Не найден системный голос. Текст ответа остаётся доступен.")
                    self.speech.say(str(text)[:10000])
                    self.response.emit(rid, json.dumps({"result": {"ok": True}}))
                except Exception:
                    self.response.emit(rid, json.dumps({"error": "Озвучивание недоступно. Используйте текст ответа."}))
            else:
                self.submit(rid, self.execute, command, payload, label=command)

        def execute(self, rid, command, payload):
            import time
            started, context = time.monotonic(), service.context
            outcome = "succeeded"
            if service.actor:
                service.content_trace.record(service.actor, "native_start", {"purpose": "ui_operation", "command": command, "correlation_id": rid})
            try:
                if command == "diagnostic_navigation":
                    if timings.enabled and service.actor:
                        timings.navigation(json.loads(payload))
                    result = {"ok": True}
                else:
                    result = service.dispatch(command, json.loads(payload))
                if command == "status":
                    result["diagnostics"] = timings.enabled
                self.response.emit(rid, json.dumps({"result": result}, ensure_ascii=False))
            except AppError as exc:
                outcome = exc.code
                self.response.emit(rid, json.dumps({"error": str(exc), "code": exc.code}, ensure_ascii=False))
            except OSError:
                outcome = "write_failed"
                self.response.emit(rid, json.dumps({"error": "Не удалось записать данные. Проверьте место и права."}))
            except Exception:
                outcome = "technical_error"
                self.response.emit(rid, json.dumps({"error": "Операция не выполнена. Данные запроса не записаны в лог."}))
            finally:
                if context == service.context and service.actor:
                    service.content_trace.record(service.actor, "native_finish", {"purpose": "ui_operation", "command": command,
                        "correlation_id": rid, "status": outcome, "duration": max(0, time.monotonic()-started)},
                        guard=lambda: context == service.context)

        def transfer_prepare(self, rid, source, destination):
            nonlocal recovery_data
            try:
                recovery_data = None
                result = transfer.prepare(source, destination)
                self.response.emit(rid, json.dumps({"result": result}, ensure_ascii=False))
            except Exception as exc:
                message = str(exc) if isinstance(exc, AppError) else "Не удалось подготовить перенос. Проверьте пути и права доступа."
                self.response.emit(rid, json.dumps({"error": message}, ensure_ascii=False))

        def transfer_execute(self, rid, command, payload):
            nonlocal transferred_executable, recovery_data
            try:
                with service.lock:
                    if service.actor:
                        raise AppError("Сначала выйдите из профиля.")
                    if command == "run_transfer":
                        if service.store.exists:
                            raise AppError("В текущей установке уже есть данные. Перезапись запрещена.")
                        args = json.loads(payload)
                        result = transfer.execute(args["operation"], args["account"], args["password"])
                        transferred_executable = Path(result["destination"]) / Path(sys.executable).name
                    elif command == "recover_transfer":
                        target = recovery_data or (transfer.plan["destination"] / "app-data" if transfer.plan else data)
                        if target == data:
                            result = Transfer.recover(target)
                        else:
                            with installation_lock(target):
                                result = Transfer.recover(target)
                        recovery_data = None
                    else:
                        from PySide6.QtCore import QProcess
                        if not transferred_executable or not transferred_executable.is_file():
                            raise AppError("Новая установка ещё не подготовлена.")
                        ok, _ = QProcess.startDetached(str(transferred_executable), [], str(transferred_executable.parent))
                        if not ok:
                            raise AppError("Не удалось запустить новую установку. Запустите её exe вручную.")
                        result = {"ok": True}
                    if command != "launch_transferred":
                        service.store.close()
                        from .storage import Store
                        from .service import identity
                        service.store = Store(data)
                        service.context = identity()
                self.response.emit(rid, json.dumps({"result": result}, ensure_ascii=False))
            except Exception as exc:
                message = str(exc) if isinstance(exc, AppError) else "Перенос не завершён. Источник сохранён. Устраните причину (место, права, формат) и очистите временную копию перед повтором."
                self.response.emit(rid, json.dumps({"error": message, "code": "transfer_failed"}, ensure_ascii=False))

        def import_selected(self, rid, path):
            try:
                from .documents import import_file
                with service.lock:
                    result = import_file(service, path)
                self.response.emit(rid, json.dumps({"result": result}, ensure_ascii=False))
            except AppError as exc:
                self.response.emit(rid, json.dumps({"error": str(exc)}, ensure_ascii=False))
            except Exception:
                self.response.emit(rid, json.dumps({"error": "Не удалось прочитать документ. Проверьте его формат."}))

    class Window(QMainWindow):
        def closeEvent(self, event):
            # Finish a serialized native operation before closing/clearing its session.
            pool.shutdown(wait=True, cancel_futures=True)
            service.network_jobs.shutdown()
            try:
                # A completed network job can still be publishing its snapshot.
                # Closing the shared SQLite connection must use the same writer lock.
                with service.lock:
                    service.logout()
            finally:
                event.accept()

    window = Window()
    window.setWindowIcon(icon)
    window.setWindowTitle("ИИ-репетитор · 7 класс")
    window.resize(1280, 880)
    profile = QWebEngineProfile("portable", window)
    profile.setPersistentStoragePath(str(data / "cache" / "webview"))
    profile.setCachePath(str(data / "cache" / "http"))
    profile.setHttpCacheType(QWebEngineProfile.HttpCacheType.MemoryHttpCache)
    profile.setPersistentCookiesPolicy(QWebEngineProfile.PersistentCookiesPolicy.NoPersistentCookies)
    interceptor = LocalOnly(profile)
    profile.setUrlRequestInterceptor(interceptor)
    view = QWebEngineView(window)
    view.setAcceptDrops(False)
    from PySide6.QtCore import Qt
    view.setContextMenuPolicy(Qt.ContextMenuPolicy.NoContextMenu)
    page = Page(profile, view)
    view.setPage(page)
    # WebEngine does not consistently propagate QStyleHints changes to CSS media
    # queries on Windows. Send the native preference as non-sensitive UI state.
    def system_theme(scheme):
        value = "dark" if scheme == Qt.ColorScheme.Dark else "light" if scheme == Qt.ColorScheme.Light else "system"
        page.runJavaScript("window.nativeColorScheme=" + json.dumps(value) + ";"
            "if(typeof applyAppearance==='function')applyAppearance("
            "document.body.dataset.colorPreference||'system',document.body.dataset.design||'strict');")

    app.styleHints().colorSchemeChanged.connect(system_theme)
    page.loadFinished.connect(lambda ok: system_theme(app.styleHints().colorScheme()) if ok else None)
    channel = QWebChannel(page)
    bridge = Bridge(channel)
    channel.registerObject("native", bridge)
    page.setWebChannel(channel)
    # No browser microphone/camera/geolocation permissions are granted.
    page.permissionRequested.connect(lambda permission: permission.deny())
    window.setCentralWidget(view)
    view.load(QUrl.fromLocalFile(str(ui / "index.html")))

    def tick():
        # Never block GUI behind a provider call; the single worker serializes accounting.
        if service.actor:
            def update():
                with service.lock:
                    try:
                        service.tick()
                    except OSError:
                        bridge.checkpointFailed.emit(True)
                    else:
                        bridge.checkpointFailed.emit(False)
            pool.submit_idle(update)

    timer = QTimer(window)
    timer.timeout.connect(tick)
    timer.start(5000)
    window.show()
    if test_hook:
        test_hook(window, page, service)
    if smoke:
        def capture():
            window.grab().save(str(data / "cache" / "smoke.png"))
            window.close()
        QTimer.singleShot(6000, capture)
    return app.exec()
