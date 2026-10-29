"""Secret-free error normalization and four real HTTP text adapters."""

import ipaddress
import ssl
import threading
import uuid
import time
import re
from urllib.parse import urlparse

import httpx

from .errors import AppError, require

DEFAULTS = {
    "openai": "https://api.openai.com/v1",
    "gigachat": "https://api.giga.chat/v1",
    "qwen": "https://dashscope-intl.aliyuncs.com/compatible-mode/v1",
    "ollama": "http://127.0.0.1:11434",
}


def validate_config(config):
    kind = config.get("kind")
    require(kind in DEFAULTS, "Выберите поддерживаемого провайдера.")
    endpoint = config.get("endpoint") or DEFAULTS[kind]
    parsed = urlparse(endpoint)
    require(parsed.hostname and not parsed.username and not parsed.password and not parsed.query
            and not parsed.fragment, "Недопустимый адрес подключения.")
    if kind == "ollama":
        try:
            local = ipaddress.ip_address(parsed.hostname).is_loopback
        except ValueError:
            local = parsed.hostname == "localhost"
        require(local and parsed.scheme in ("http", "https"),
                "В этой версии Ollama подключается только к локальному компьютеру.")
    else:
        require(parsed.scheme == "https", "Облачное подключение требует HTTPS.")
        allowed = {
            "openai": {"api.openai.com"},
            "gigachat": {"api.giga.chat", "gigachat.devices.sberbank.ru"},
            "qwen": {"dashscope-intl.aliyuncs.com", "dashscope.aliyuncs.com",
                     "dashscope-us.aliyuncs.com"},
        }
        require(parsed.hostname in allowed[kind], "Endpoint не входит в список адресов этого провайдера.")
        require(bool(config.get("secret")), "Введите ключ подключения.")
    require(1 <= int(config.get("timeout", 60)) <= 180, "Тайм-аут должен быть от 1 до 180 секунд.")
    require(0 < len(config.get("model", "")) <= 160, "Укажите модель.")
    return {**config, "endpoint": endpoint.rstrip("/")}


class Provider:
    def __init__(self, config, transport=None):
        self.config = validate_config(config)
        self.cancelled = threading.Event()
        self.usage = None
        self.token = None
        self.token_expires = 0
        self.permission_check = lambda: True
        # System trust is respected (including installed enterprise/GigaChat CA).
        # No verify=False, redirects or ambient HTTP proxy credentials.
        self.client = httpx.Client(timeout=int(config.get("timeout", 60)),
                                   verify=ssl.create_default_context(), trust_env=False,
                                   follow_redirects=False, transport=transport)

    def close(self):
        self.client.close()

    def request(self, method, url, **kwargs):
        def observe(stage, payload):
            if url.endswith(("/chat/completions", "/api/chat")) and hasattr(self, "observe"):
                try:
                    self.observe(stage, payload)
                except Exception:
                    pass  # Diagnostics must not change a provider outcome.
        try:
            require(self.permission_check() and not self.cancelled.is_set(), 'Запрос отменён.', 'cancelled')
            observe("transport_send", {"payload": kwargs.get("json"), "method": method})
            with self.client.stream(method, url, **kwargs) as response:
                self.last_http_status = response.status_code
                observe("transport_status", {"http_status": response.status_code})
                if response.status_code in (401, 403):
                    raise AppError("Проверьте ключ подключения и доступ к модели.", "authorization")
                if response.status_code == 429:
                    raise AppError("Лимит запросов или квота провайдера исчерпаны.", "quota")
                if response.status_code >= 500:
                    raise AppError("Сервис ИИ временно недоступен.", "network")
                require(200 <= response.status_code < 300,
                        "Провайдер отклонил запрос. Проверьте модель и настройки.", "provider")
                chunks, size = [], 0
                for chunk in response.iter_bytes():
                    require(not self.cancelled.is_set(), "Запрос отменён.", "cancelled")
                    size += len(chunk)
                    require(size <= 4 * 1024 * 1024, "Ответ сервиса слишком велик.", "provider")
                    chunks.append(chunk)
                import json
                decoded = json.loads(b"".join(chunks))
                observe("transport_receive", {"http_status": response.status_code, "payload": decoded})
                return decoded
        except httpx.TimeoutException as exc:
            raise AppError("Сервис ИИ не ответил вовремя.", "timeout") from exc
        except httpx.HTTPError as exc:
            raise AppError("Не удалось установить защищённое соединение с ИИ.", "network") from exc
        except (ValueError, KeyError, TypeError) as exc:
            raise AppError("Сервис вернул некорректный ответ.", "provider") from exc

    def headers(self):
        secret = self.config.get("secret", "")
        if self.config["kind"] == "gigachat":
            scope = self.config.get("scope", "GIGACHAT_API_PERS")
            require(scope in ("GIGACHAT_API_PERS", "GIGACHAT_API_B2B", "GIGACHAT_API_CORP"),
                    "Неизвестный scope GigaChat.")
            if self.token and time.time() < self.token_expires - 30:
                return {"Authorization": f"Bearer {self.token}"}
            token = self.request("POST", "https://ngw.devices.sberbank.ru:9443/api/v2/oauth",
                                 headers={"Authorization": f"Basic {secret}", "RqUID": str(uuid.uuid4())},
                                 data={"scope": scope})
            secret = token.get("access_token")
            require(isinstance(secret, str) and bool(secret), "Не удалось получить токен GigaChat.", "provider")
            self.token = secret
            self.token_expires = float(token.get('expires_at', 0)) / 1000
        return {"Authorization": f"Bearer {secret}"} if secret else {}

    def get_capabilities(self):
        return {"text": True, "vision": False, "audio": False, "tools": False,
                "structured_output": False, "streaming": False, "context": None,
                "source": "Минимальный текстовый контракт; остальные возможности не проверены"}

    def list_models(self):
        local = self.config["kind"] == "ollama"
        result = self.request("GET", self.config["endpoint"] + ("/api/tags" if local else "/models"),
                              headers=self.headers())
        field = "models" if local else "data"
        return [m.get("name" if local else "id") for m in result.get(field, [])][:300]

    def send_message(self, messages):
        local = self.config["kind"] == "ollama"
        path = "/api/chat" if local else "/chat/completions"
        body = {"model": self.config["model"], "messages": messages, "stream": False}
        result = self.request("POST", self.config["endpoint"] + path, headers=self.headers(), json=body)
        try:
            if local:
                content = result["message"]["content"]
                usage = {"input_tokens": result.get("prompt_eval_count"),
                         "output_tokens": result.get("eval_count")}
            else:
                content = result["choices"][0]["message"]["content"]
                usage = result.get("usage")
            require(isinstance(content, str) and bool(content.strip()), "Модель вернула пустой ответ.", "provider")
            self.usage = usage
            require(len(content) <= 100_000, "Ответ превышает 100 000 символов. Разбейте запрос.", "capacity")
            return {"text": content, "usage": usage,
                    "finish_reason": result.get("done_reason") if local else result["choices"][0].get("finish_reason"),
                    "http_status": getattr(self, "last_http_status", None)}
        except (KeyError, IndexError, TypeError) as exc:
            raise AppError("Формат ответа модели не поддерживается.", "provider") from exc

    def validate_configuration(self):
        return self.send_message([{"role": "user", "content": "Ответь одним словом: готово"}])

    def send_multimodal(self, messages, images):
        require(self.config['kind'] == 'gigachat',
                'OCR изображений в этом выпуске подключён через GigaChat. Доступен ручной ввод текста.', 'unsupported')
        require(isinstance(images, list) and 0 < len(images) <= 10, 'Прикрепите от 1 до 10 изображений.')
        uploaded = []
        cleanup_failed = False
        try:
            for image in images:
                raw, mime = image['bytes'], image['mime']
                require(len(raw) <= 8*1024*1024 and mime in ('image/png', 'image/jpeg'), 'Используйте PNG/JPEG до 8 МБ.')
                file = self.request('POST', self.config['endpoint']+'/files', headers=self.headers(),
                    files={'file': ('page.png' if mime == 'image/png' else 'page.jpg', raw, mime)}, data={'purpose': 'general'})
                fid = file.get('id', '')
                require(isinstance(fid, str) and re.fullmatch(r'[\w-]{1,100}', fid), 'Некорректный ID файла.', 'provider')
                uploaded.append(fid)
            request_messages = [dict(m) for m in messages]
            request_messages[-1]['attachments'] = list(uploaded)
            result = self.request('POST', self.config['endpoint']+'/chat/completions', headers=self.headers(),
                json={'model': self.config['model'], 'messages': request_messages, 'stream': False})
            content = result['choices'][0]['message']['content']
            require(isinstance(content, str) and content.strip() and len(content) <= 30000,
                    'Распознанный текст пуст или превышает 30 000 символов.', 'unsupported_format')
            self.usage = result.get('usage')
        finally:
            # Deletion is permitted even after consent revocation: it reduces remote retention.
            permission, cancelled = self.permission_check, self.cancelled.is_set()
            self.permission_check = lambda: True
            self.cancelled.clear()
            for fid in uploaded:
                try:
                    self.request('POST', self.config['endpoint']+'/files/'+fid+'/delete', headers=self.headers())
                except Exception:
                    cleanup_failed = True
            self.permission_check = permission
            if cancelled:
                self.cancelled.set()
        return {'text': content, 'usage': self.usage, 'cleanup_failed': cleanup_failed}

    def cancel_request(self):
        self.cancelled.set()

    def stream_response(self, *_):
        raise AppError("Потоковый режим в этом адаптере ещё не подключён.", "unsupported")

    def get_usage(self):
        return self.usage
