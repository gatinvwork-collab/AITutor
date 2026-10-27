"""Reviewed starter exercises and bounded independent checking; never eval code."""

import ast
import operator
from fractions import Fraction

from .errors import require

SUBJECTS = {"algebra": "Алгебра", "geometry": "Геометрия", "physics": "Физика", "informatics": "Информатика"}


def subjects_for_grade(grade=7):
    return dict(SUBJECTS) if grade >= 7 else {"math": "Математика"}

# A starter catalog, explicitly not a full approved school curriculum.
TOPICS = [
    {"id": "math-equations", "subject": "algebra", "title": "Линейные уравнения",
     "theory": "Чтобы решить линейное уравнение, выполни одинаковые преобразования обеих частей. "
               "После нахождения корня подставь его в исходное уравнение.",
     "tasks": [("Реши уравнение 3x + 5 = 20. Введи значение x.", "5"),
               ("Реши уравнение 4x − 7 = 9.", "4"), ("Реши уравнение 2x + 8 = 2.", "-3")],
     "hints": ["Какая операция поможет убрать слагаемое без x?",
               "Выполни обратную операцию с числом в обеих частях.",
               "После переноса чисел раздели обе части на коэффициент при x."]},
    {"id": "math-powers", "subject": "algebra", "title": "Степень с натуральным показателем",
     "theory": "Степень aⁿ — произведение n одинаковых множителей a. Сначала вычисляют степень, затем сумму.",
     "tasks": [("Вычисли 2⁵.", "32"), ("Вычисли 3³ + 2.", "29"), ("Вычисли 5² − 4².", "9")],
     "hints": ["Что означает показатель степени?", "Запиши степень как произведение.",
               "Сначала вычисли каждую степень отдельно, затем выполни оставшиеся действия."]},
    {"id": "math-fractions", "subject": "algebra", "title": "Дроби и рациональные числа",
     "theory": "При сложении дробей сначала приведи их к общему знаменателю. Ответ можно записать дробью.",
     "tasks": [("Вычисли 1/3 + 1/6.", "1/2"), ("Вычисли 3/4 − 1/8.", "5/8"),
               ("Вычисли (−2/3) · (3/4).", "-1/2")],
     "hints": ["Нужен ли общий знаменатель?", "Проверь знаки и порядок действий.",
               "Умножь числитель и знаменатель каждой дроби на нужный множитель."]},
    {"id": "geometry-basics", "subject": "geometry", "title": "Прямые, лучи и углы",
     "theory": "Через две различные точки проходит одна прямая. Развёрнутый угол равен 180°, "
               "прямой — 90°. Градусная мера показывает величину угла.",
     "tasks": [("Прямой угол разделили на углы 35° и x°. Найди x; укажи градусы.", "55 °"),
               ("Развёрнутый угол разделили на 65° и x°. Найди x в градусах.", "115 °"),
               ("Углы 20°, 35° и x° вместе составляют прямой угол. Найди x в градусах.", "35 °")],
     "hints": ["Какова величина всего угла?", "Запиши сумму частей, равную 90° или 180°.",
               "Вычти из величины всего угла сумму известных частей."]},
    {"id": "geometry-adjacent", "subject": "geometry", "title": "Смежные и вертикальные углы",
     "theory": "Смежные углы в сумме дают 180°. Вертикальные углы равны. "
               "Перед вычислением определи, какое из двух свойств применимо.",
     "tasks": [("Один из смежных углов равен 70°. Найди другой в градусах.", "110 °"),
               ("Один угол равен 48°. Чему равен вертикальный ему угол? Укажи градусы.", "48 °"),
               ("Смежные углы относятся как 2:3. Найди меньший в градусах.", "72 °")],
     "hints": ["Эти углы смежные или вертикальные?", "Смежные: сумма 180°. Вертикальные: равны.",
               "В отношении 2:3 весь развёрнутый угол содержит 5 одинаковых частей."]},
    {"id": "geometry-triangles", "subject": "geometry", "title": "Треугольники и сумма углов",
     "theory": "Сумма углов треугольника равна 180°. У равнобедренного треугольника "
               "углы при основании равны. У прямоугольного один угол равен 90°.",
     "tasks": [("В треугольнике два угла равны 50° и 60°. Найди третий в градусах.", "70 °"),
               ("Угол при вершине равнобедренного треугольника равен 40°. Найди угол при основании.", "70 °"),
               ("Один острый угол прямоугольного треугольника равен 27°. Найди второй в градусах.", "63 °")],
     "hints": ["Какова сумма углов треугольника?", "Вычти известные углы из 180°.",
               "В равнобедренном треугольнике оставшаяся сумма делится на два равных угла."]},
    {"id": "physics-speed", "subject": "physics", "title": "Равномерное движение",
     "theory": "При равномерном движении скорость постоянна: v = s / t. Единица СИ скорости — м/с.",
     "tasks": [("Тело прошло 120 м за 20 с. Найди скорость в м/с (добавь единицу).", "6 м/с"),
               ("Тело прошло 90 м за 30 с. Найди скорость в м/с.", "3 м/с"),
               ("Тело прошло 240 м за 60 с. Найди скорость в м/с.", "4 м/с")],
     "hints": ["Какие величины известны?", "Используй v = s / t.",
               "Раздели путь в метрах на время в секундах; укажи м/с."]},
    {"id": "physics-density", "subject": "physics", "title": "Плотность вещества",
     "theory": "Плотность ρ = m / V. При массе в кг и объёме в м³ плотность выражается в кг/м³.",
     "tasks": [("Масса 12 кг, объём 3 м³. Найди плотность в кг/м³.", "4 кг/м³"),
               ("Масса 30 кг, объём 5 м³. Найди плотность в кг/м³.", "6 кг/м³"),
               ("Масса 21 кг, объём 3 м³. Найди плотность в кг/м³.", "7 кг/м³")],
     "hints": ["Плотность связывает массу и объём.", "Используй ρ = m / V.",
               "Раздели массу на объём и запиши единицу кг/м³."]},
    {"id": "informatics-binary", "subject": "informatics", "title": "Двоичная система счисления",
     "theory": "Разряды двоичного числа справа налево имеют веса 1, 2, 4, 8… Сложи веса разрядов с единицами.",
     "tasks": [("Запиши двоичное 101₂ в десятичной системе.", "5"),
               ("Запиши двоичное 110₂ в десятичной системе.", "6"),
               ("Запиши двоичное 1001₂ в десятичной системе.", "9")],
     "hints": ["Начни с правого разряда.", "Веса разрядов: 1, 2, 4, 8…",
               "Сложи только веса тех разрядов, где стоит 1."]},
    {"id": "informatics-logic", "subject": "informatics", "title": "Логические операции",
     "theory": "И истинно, когда оба условия истинны. ИЛИ истинно, когда истинно хотя бы одно. НЕ меняет значение.",
     "tasks": [("Чему равно ИСТИНА И ЛОЖЬ? Введи истина или ложь.", "ложь"),
               ("Чему равно ИСТИНА ИЛИ ЛОЖЬ?", "истина"), ("Чему равно НЕ ИСТИНА?", "ложь")],
     "hints": ["Вспомни правило указанной операции.", "Для И должны быть истинны оба условия.",
               "Для ИЛИ достаточно одного истинного условия; НЕ меняет значение на противоположное."]},
]


def topic(identity):
    found = next((t for t in TOPICS if t["id"] == identity), None)
    require(found is not None, "Тема не найдена.")
    return found


def catalog():
    return [{k: t[k] for k in ("id", "subject", "title", "theory")} for t in TOPICS]


def catalog_subject(record):
    """Classify legacy math without rewriting its historical subject/snapshots."""
    if record.get("subject") == "math":
        found = next((t for t in TOPICS if t["id"] == record.get("topic")), None)
        return found["subject"] if found else "math_archive"
    return record.get("subject")


def arithmetic(text):
    require(len(text) <= 150, "Слишком длинное выражение.")
    tree = ast.parse(text.replace(",", ".").replace("−", "-"), mode="eval")
    require(sum(1 for _ in ast.walk(tree)) < 60, "Слишком сложное выражение.")
    ops = {ast.Add: operator.add, ast.Sub: operator.sub, ast.Mult: operator.mul, ast.Div: operator.truediv}

    def walk(node):
        if isinstance(node, ast.Constant) and type(node.value) in (int, float):
            require(abs(node.value) < 10**12, "Число вне поддерживаемого диапазона.")
            return Fraction(str(node.value))
        if isinstance(node, ast.UnaryOp) and isinstance(node.op, (ast.USub, ast.UAdd)):
            return -walk(node.operand) if isinstance(node.op, ast.USub) else walk(node.operand)
        if isinstance(node, ast.BinOp) and type(node.op) in ops:
            return ops[type(node.op)](walk(node.left), walk(node.right))
        raise ValueError("Unsupported expression")

    return walk(tree.body)


def check_answer(answer, expected):
    answer = answer.strip().lower().replace("x=", "").replace("x =", "").replace("ё", "е")
    expected = expected.lower()
    if " " in expected:
        number, unit = expected.split(" ", 1)
        if unit == "°":
            answer = answer.replace("градусов", "°").replace("градуса", "°").replace("градус", "°")
        normalized = answer.replace(" ", "").replace("^3", "³").replace("м3", "м³")
        if not normalized.endswith(unit):
            return {"status": "incorrect", "error": "units", "message": "Проверь единицу измерения."}
        answer = normalized[:-len(unit)]
        expected = number
    try:
        correct = arithmetic(answer) == arithmetic(expected)
    except Exception:
        if expected in ("истина", "ложь"):
            correct = answer == expected
        else:
            return {"status": "unknown", "error": "format", "message": "Не удалось разобрать ответ. "
                    "Введи число, дробь или выражение; для физики добавь указанную единицу."}
    return {"status": "verified" if correct else "incorrect", "error": None if correct else "calculation",
            "message": "Верно. Проверено независимо от ИИ." if correct else "Пока не сходится. Проверь вычисления."}


def analyze_code(code):
    require(len(code) <= 30_000, "Слишком большой фрагмент кода.")
    try:
        tree = ast.parse(code)
    except SyntaxError as exc:
        return f"Синтаксическая ошибка Python, строка {exc.lineno}: {exc.msg}. Код не исполнялся."
    risky = any(isinstance(n, (ast.Import, ast.ImportFrom, ast.Call)) for n in ast.walk(tree))
    return ("Синтаксис Python корректен. Логика и результаты не подтверждены. Код не исполнялся."
            + (" Есть вызовы или импорты; доступ к системе не предоставлен." if risky else ""))
