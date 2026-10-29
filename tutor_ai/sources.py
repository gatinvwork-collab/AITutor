"""Public HTTPS retrieval with pinned, globally routable DNS on every redirect."""

import http.client
import ipaddress
import re
import socket
import ssl
import time
from html import unescape
from urllib.parse import quote, urljoin, urlparse
from xml.etree import ElementTree

from .errors import AppError, require


class PublicConnection(http.client.HTTPSConnection):
    def connect(self):
        addresses = socket.getaddrinfo(self.host, self.port, type=socket.SOCK_STREAM)
        ips = [ipaddress.ip_address(a[4][0]) for a in addresses]
        require(
            addresses
            and all(
                ip.is_global
                and not (
                    ip.is_multicast
                    or ip.is_reserved
                    or ip.is_unspecified
                    or ip.is_loopback
                    or ip.is_link_local
                )
                for ip in ips
            ),
            "Загрузка локальных и внутренних адресов запрещена.",
            "source_unavailable",
        )
        # Connect to the vetted IP, verify the original hostname. No second DNS lookup.
        address = addresses[0]
        sock = socket.socket(address[0], address[1], address[2])
        try:
            sock.settimeout(self.timeout)
            sock.connect(address[4])
            self.sock = self._context.wrap_socket(sock, server_hostname=self.host)
        except Exception:
            sock.close()
            raise


def fetch(url, limit=8 * 1024 * 1024, cancel=None, budget=40):
    started = time.monotonic()
    try:
        for _ in range(5):
            parsed = urlparse(url)
            require(
                parsed.scheme == "https"
                and parsed.hostname
                and parsed.port in (None, 443)
                and not parsed.username
                and not parsed.password
                and not parsed.fragment,
                "Разрешён только публичный HTTPS-источник.",
                "source_unavailable",
            )
            connection = PublicConnection(parsed.hostname, timeout=15, context=ssl.create_default_context())
            try:
                path = parsed.path or "/"
                connection.request(
                    "GET",
                    path + ("?" + parsed.query if parsed.query else ""),
                    headers={"Accept-Encoding": "identity", "User-Agent": "Tutor-AI/0.5"},
                )
                response = connection.getresponse()
                if response.status in (301, 302, 303, 307, 308):
                    url = urljoin(url, response.getheader("Location", ""))
                    continue
                require(response.status == 200, f"Источник вернул HTTP {response.status}.",
                        "source_forbidden" if response.status == 403 else "source_http_error")
                require(
                    response.getheader("Content-Encoding", "identity") == "identity",
                    "Сжатый ответ не поддерживается.",
                    "source_unavailable",
                )
                content_type = response.getheader("Content-Type", "").split(";")[0].lower()
                require(
                    content_type
                    in (
                        "text/html",
                        "text/plain",
                        "application/pdf",
                        "application/xml",
                        "text/xml",
                        "application/rss+xml",
                    ),
                    "Формат источника не поддерживается.",
                    "unsupported_format",
                )
                data = bytearray()
                while True:
                    require(not cancel or not cancel.is_set(), "Загрузка отменена.", "cancelled")
                    require(time.monotonic() - started < budget, "Время загрузки истекло.", "source_timeout")
                    chunk = response.read(min(65536, limit + 1 - len(data)))
                    if not chunk:
                        return bytes(data), content_type, url
                    data.extend(chunk)
                    require(
                        len(data) <= limit, "Источник слишком велик. Выберите отдельный документ.", "capacity"
                    )
            finally:
                connection.close()
        raise AppError("Слишком много перенаправлений.", "source_unavailable")
    except (OSError, http.client.HTTPException, ValueError) as exc:
        raise AppError("Не удалось безопасно загрузить источник.", "source_unavailable") from exc


def extract(raw, content_type):
    if content_type == "application/pdf":
        import io
        from pypdf import PdfReader

        reader = PdfReader(io.BytesIO(raw))
        require(not reader.is_encrypted and len(reader.pages) <= 30, "PDF: до 30 страниц без пароля.")
        value = "\n".join(p.extract_text() or "" for p in reader.pages)
    else:
        value = raw.decode("utf-8", errors="replace")
        value = re.sub(r"<(script|style)\b[^>]*>.*?</\1>", "", value, flags=re.I | re.S)
        value = unescape(re.sub(r"<[^>]*>", " ", value))
    require(
        0 < len(value.strip()) <= 30000, "Текст источника пуст или длиннее 30 000 символов. Выберите раздел."
    )
    return value.strip()


def search(query):
    raw, _, _ = fetch(
        "https://www.bing.com/search?q=" + quote(query) + "&format=rss&setlang=ru-RU", 1024 * 1024
    )
    require(
        b"<!DOCTYPE" not in raw.upper() and b"<!ENTITY" not in raw.upper(), "Неподдерживаемый ответ поиска."
    )
    try:
        root = ElementTree.fromstring(raw)
        candidates = [
            {"title": i.findtext("title"), "url": i.findtext("link")}
            for i in root.findall(".//item")
            if (i.findtext("link") or "").startswith("https://")
        ][:10]
        # Public search can return unrelated/cached results. Do not present those
        # as identified books or federal curricula merely because HTTP succeeded.
        terms = set(re.findall(r"[^\W\d_]{4,}", query.casefold())) - {"класс", "учебник", "учебники"}
        minimum = min(2, len(terms))
        return [
            c
            for c in candidates
            if terms
            and sum(t in (str(c["title"]) + " " + str(c["url"])).casefold() for t in terms) >= minimum
        ]
    except ElementTree.ParseError as exc:
        raise AppError(
            "Поиск не вернул список источников. Укажите ссылку вручную.", "source_unavailable"
        ) from exc
