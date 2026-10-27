"""Human-readable audit DTOs; identity keys remain authoritative."""

LABELS = {
    "profile_updated": "Изменены данные профиля",
    "profile_renamed": "Изменено имя профиля",
    "register": "Создан профиль", "login": "Вход в профиль", "logout": "Выход из профиля",
    "recover_parent": "Восстановлен доступ родителя", "reset_student_password": "Сброшен пароль ученика",
    "change_password": "Изменён пароль", "rotate_recovery": "Перевыпущен ключ восстановления",
    "create_link_invite": "Создан код семейной связи", "confirm_link": "Подтверждена семейная связь",
    "provider_and_consent_changed": "Изменены подключение ИИ и разрешения",
    "time_limit_changed": "Изменён лимит времени", "program_decision": "Рассмотрен запрос учебника",
    "backup_created": "Создана резервная копия", "delete_student": "Удалён профиль ученика",
}


def identity_snapshot(store, uid):
    user = store.user(uid) if uid else None
    return {"name": user["name"], "role": user["role"]} if user else None


def present(store, event):
    result = {**event, "label": LABELS.get(event["event"], "Событие безопасности")}
    for field in ("actor", "target"):
        current = identity_snapshot(store, event.get(field))
        snapshot = event.get(field + "_snapshot")
        result[field + "_display"] = (snapshot or current) if current else None
        result[field + "_display"] = result[field + "_display"] or {
            "name": "Приложение" if not event.get(field) else "Удалённый или недоступный профиль", "role": None}
        if snapshot and current and snapshot["name"] != current["name"]:
            result[field + "_current_name"] = current["name"]
    return result
