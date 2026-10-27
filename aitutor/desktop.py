"""Qt WebView host: fixed bridge, local resources and native file selection."""

import json
import os
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from .errors import AppError
from .service import Service


def portable_root():
    return Path(sys.executable).resolve().parent if getattr(sys, "frozen", False) else Path(__file__).resolve().parent.parent


def run(smoke=False, root_override=None, service_factory=Service, test_hook=None):
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
    app.setApplicationName("AI-Tutor")
    app.setOrganizationName("AITutor")
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
    pool = ThreadPoolExecutor(max_workers=1, thread_name_prefix="native-command")

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

        @Slot(str, str, str)
        def request(self, rid, command, payload):
            if len(payload) > 200_000 or len(rid) > 100:
                self.response.emit(rid, json.dumps({"error": "Запрос слишком велик."}))
                return
            if command == "cancel_request":
                result = service.cancel_request()
                self.response.emit(rid, json.dumps({"result": result}))
            elif command == "pick_file":
                if not service.actor:
                    self.response.emit(rid, json.dumps({"error": "Сначала войдите."}))
                    return
                path, _ = QFileDialog.getOpenFileName(window, "Выбрать задание", "",
                    "Учебные материалы (*.txt *.py *.csv *.pdf *.docx *.png *.jpg *.jpeg *.webp)")
                if not path:
                    self.response.emit(rid, json.dumps({"result": None}))
                    return
                pool.submit(self.import_selected, rid, path)
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
                pool.submit(self.execute, rid, command, payload)

        def execute(self, rid, command, payload):
            try:
                result = service.dispatch(command, json.loads(payload))
                self.response.emit(rid, json.dumps({"result": result}, ensure_ascii=False))
            except AppError as exc:
                self.response.emit(rid, json.dumps({"error": str(exc), "code": exc.code}, ensure_ascii=False))
            except OSError:
                self.response.emit(rid, json.dumps({"error": "Не удалось записать данные. Проверьте место и права."}))
            except Exception:
                self.response.emit(rid, json.dumps({"error": "Операция не выполнена. Данные запроса не записаны в лог."}))

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
            try:
                service.logout()
            finally:
                event.accept()

    window = Window()
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
                    service.tick()
            pool.submit(update)

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
