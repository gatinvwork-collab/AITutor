"""Exact, nonexecuting checkers with explicit, deliberately narrow scope."""

import ast
import re
from fractions import Fraction

from .education import arithmetic

VERSION = "linear-rational-v1"


def linear(expression):
    value = expression.strip().replace("−", "-").replace(",", ".")
    value = re.sub(r"(\d|\))\s*x", r"\1*x", value)
    root = ast.parse(value, mode="eval")
    if len(value) > 300 or sum(1 for _ in ast.walk(root)) > 100:
        raise ValueError("size")

    def walk(node):
        if isinstance(node, ast.Constant) and type(node.value) in (int, float) and abs(node.value) <= 10**12:
            literal = ast.get_source_segment(value, node)
            if not literal or len(literal) > 40 or not re.fullmatch(r"(?:\d+(?:\.\d*)?|\.\d+)", literal):
                raise ValueError("unsupported numeric literal")
            number = Fraction(literal)
            if abs(number) > 10**12:
                raise ValueError("number too large")
            return Fraction(0), number
        if isinstance(node, ast.Name) and node.id == "x":
            return Fraction(1), Fraction(0)
        if isinstance(node, ast.UnaryOp) and isinstance(node.op, (ast.USub, ast.UAdd)):
            a, b = walk(node.operand)
            return (-a, -b) if isinstance(node.op, ast.USub) else (a, b)
        if isinstance(node, ast.BinOp):
            a, b = walk(node.left)
            c, d = walk(node.right)
            if isinstance(node.op, ast.Add):
                return a + c, b + d
            if isinstance(node.op, ast.Sub):
                return a - c, b - d
            if isinstance(node.op, ast.Mult) and not (a and c):
                return a * d + b * c, b * d
            if isinstance(node.op, ast.Div) and not c and d:
                return a / d, b / d
        raise ValueError("unsupported")

    return walk(root.body)


def equation(expression):
    left, right = expression.split("=")
    a, b = linear(left)
    c, d = linear(right)
    a, b = a - c, b - d
    return ("root", -b / a) if a else ("all" if not b else "none", None)


def inspect_steps(solution):
    """Only compares equations actually supplied; never claims task/rubric proof."""
    lines = [s.strip() for s in re.split(r"[;\n]", solution) if s.strip()]
    if not 2 <= len(lines) <= 50:
        return {
            "status": "unknown",
            "scope": "equation_transitions",
            "reason": "unsupported_format",
            "checker": VERSION,
        }
    try:
        roots = [equation(line) for line in lines]
        for index in range(1, len(roots)):
            if roots[index] != roots[index - 1]:
                return {
                    "status": "incorrect",
                    "scope": "equation_transitions",
                    "step": index + 1,
                    "message": "Переход меняет множество решений.",
                    "checker": VERSION,
                }
        return {
            "status": "verified",
            "scope": "equation_transitions",
            "checker": VERSION,
            "message": "Поданные линейные уравнения равносильны. Соответствие условию и вся рубрика этим не доказаны.",
        }
    except (ValueError, SyntaxError, ZeroDivisionError, OverflowError):
        return {
            "status": "unknown",
            "scope": "equation_transitions",
            "reason": "unsupported_format",
            "checker": VERSION,
        }


def formal_value(statement, answer):
    """Compute from the actual, strictly recognized question, not an AI answer key."""
    match = re.fullmatch(r"Вычисли\s+([\d\s+*/().,−-]+)[.!]?", statement.strip())
    if match:
        try:
            expected = arithmetic(match.group(1).rstrip("."))
            candidate = re.sub(r"^x\s*=\s*", "", answer.strip(), count=1)
            correct = arithmetic(candidate) == expected
            return {
                "status": "verified" if correct else "incorrect",
                "scope": "numeric_result",
                "checker": VERSION,
            }
        except Exception:
            pass
    return {
        "status": "unknown",
        "scope": "numeric_result",
        "reason": "unsupported_format",
        "checker": VERSION,
    }
