"""Native, bounded Photon/OSM address directory (not the official FIAS registry)."""

import json
import time
from datetime import datetime, timezone

import httpx

from .errors import AppError, require

SOURCE = "Photon / OpenStreetMap"
SOURCE_URL = "https://www.openstreetmap.org/copyright"
ENDPOINT = "https://photon.komoot.io"


def normalized(text):
    return " ".join(text.casefold().replace("ё", "е").split())


class AddressDirectory:
    def __init__(self, transport=None, clock=time.monotonic):
        self.transport = transport
        self.clock = clock
        self.last_request = -float("inf")
        self.cache = {}
        self.entries = {}

    def search(self, kind, query, region_id=None):
        require(kind in ("region", "city"), "Неизвестный тип адресного поиска.")
        require(isinstance(query, str) and 2 <= len(query.strip()) <= 100, "Введите от 2 до 100 символов.")
        region = self.entries.get(region_id) if kind == "city" else None
        require(kind != "city" or (region and region["kind"] == "region"), "Сначала выберите регион из подсказок.")
        key = (kind, normalized(query), region_id)
        cached = self.cache.get(key)
        if cached and self.clock() - cached[0] < 900:
            return cached[1]
        require(self.clock() - self.last_request >= 1, "Подождите секунду и повторите поиск.", "rate_limit")
        self.last_request = self.clock()
        # The public instance supports "default", not "ru"; default returns
        # local OSM names (Russian for these RU address records).
        params = {"countrycode": "RU", "limit": 12, "lang": "default"}
        if kind == "region":
            path = "/api/"
            params.update(q=query.strip(), layer="state")
        else:
            path = "/structured/"
            params.update(state=region["name"], city=query.strip(), layer="city")
        try:
            with httpx.Client(timeout=8, follow_redirects=False, trust_env=False,
                              transport=self.transport) as client:
                with client.stream("GET", ENDPOINT + path, params=params,
                                   headers={"User-Agent": "AITutor/0.2 (educational pilot)",
                                            "Accept": "application/json"}) as response:
                    require(response.status_code == 200,
                            "Адресный сервис недоступен. Повторите поиск или включите ручной ввод.", "address_network")
                    chunks, size = [], 0
                    for chunk in response.iter_bytes():
                        size += len(chunk)
                        require(size <= 512 * 1024, "Слишком большой ответ адресного сервиса.", "address_network")
                        chunks.append(chunk)
                    data = json.loads(b"".join(chunks))
        except (httpx.HTTPError, ValueError) as exc:
            raise AppError("Не удалось получить адреса. Проверьте интернет или выберите ручной ввод.",
                           "address_network") from exc
        require(isinstance(data, dict) and isinstance(data.get("features"), list),
                "Некорректный ответ адресного справочника.", "address_network")
        found = []
        for feature in data["features"][:40]:
            props = feature.get("properties", {}) if isinstance(feature, dict) else {}
            if not isinstance(props, dict):
                continue
            name = props.get("name")
            if props.get("countrycode", "").upper() != "RU" or not isinstance(name, str) or len(name) > 200:
                continue
            if not isinstance(props.get("osm_id"), int) or props.get("osm_type") not in ("N", "W", "R"):
                continue
            if kind == "region" and props.get("type") != "state":
                continue
            if kind == "city":
                if props.get("type") not in ("city", "locality"):
                    continue
                # Never accept a same-name place in another region. Federal cities
                # may be both region and city without a separate state property.
                state_name = props.get("state")
                if normalized(state_name or name) != normalized(region["name"]):
                    continue
            eid = f'osm:{props["osm_type"]}:{props["osm_id"]}'
            label = ", ".join(dict.fromkeys(str(v) for v in
                              (name, props.get("county"), props.get("state")) if v))
            record = {"id": eid, "kind": kind, "name": name, "label": label,
                      "region_id": region_id if kind == "city" else None, "source": SOURCE,
                      "source_url": SOURCE_URL, "retrieved_at": datetime.now(timezone.utc).isoformat()}
            # Prefix the kind: a federal city can share an OSM ID with its region.
            record["id"] = kind + ":" + eid
            self.entries[record["id"]] = record
            if not any(r["id"] == record["id"] for r in found):
                found.append(record)
        result = {"items": found, "source": SOURCE, "source_url": SOURCE_URL,
                  "message": "Выберите запись из списка." if found else
                             "Ничего не найдено. Уточните запрос или используйте ручной ввод."}
        if len(self.cache) >= 128:
            self.cache.pop(next(iter(self.cache)))
        self.cache[key] = (self.clock(), result)
        return result

    def validate_profile(self, profile):
        address = profile.get("address")
        require(address is None or isinstance(address, dict), "Некорректный адрес.")
        if not address or address.get("mode") == "manual":
            return {**profile, "address": {"mode": "manual", "verification": "manual_unverified"}}
        require(isinstance(address, dict) and address.get("mode") == "catalog", "Некорректный адрес.")
        region = self.entries.get(address.get("region_id"))
        city = self.entries.get(address.get("city_id"))
        require(region and city and region["kind"] == "region" and city["kind"] == "city"
                and city["region_id"] == region["id"],
                "Выберите согласованные регион и город из подсказок или включите ручной ввод.")
        return {**profile, "region": region["name"], "city": city["name"],
                "address": {"mode": "catalog", "verification": "catalog_selected", "region": region,
                            "city": city, "source": SOURCE}}
