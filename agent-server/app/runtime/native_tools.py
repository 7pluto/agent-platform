from __future__ import annotations

import ast
from datetime import datetime, timezone
from typing import Any

from app.core.errors import ApiError


class NativeToolRegistry:
    """The only V1 tool execution surface; no user code is loaded."""

    names = {"current_time", "calculator", "echo"}

    async def invoke(self, name: str, arguments: dict[str, Any]) -> dict[str, Any]:
        if name == "current_time":
            return {"utc": datetime.now(timezone.utc).isoformat()}
        if name == "echo":
            return {"value": arguments.get("value", "")}
        if name == "calculator":
            expression = str(arguments.get("expression", ""))
            return {"value": self._calculate(expression)}
        raise ApiError(404, "NATIVE_TOOL_NOT_FOUND", "native tool was not found")

    @staticmethod
    def _calculate(expression: str) -> float:
        try:
            node = ast.parse(expression, mode="eval")
        except SyntaxError as exc:
            raise ApiError(422, "INVALID_CALCULATOR_EXPRESSION", "invalid calculator expression") from exc
        allowed = (ast.Expression, ast.BinOp, ast.UnaryOp, ast.Constant, ast.Add, ast.Sub, ast.Mult, ast.Div, ast.Mod, ast.Pow, ast.USub, ast.UAdd)
        if not all(isinstance(item, allowed) for item in ast.walk(node)):
            raise ApiError(422, "INVALID_CALCULATOR_EXPRESSION", "calculator supports numbers and arithmetic only")
        result = eval(compile(node, "<calculator>", "eval"), {"__builtins__": {}}, {})
        if not isinstance(result, (int, float)):
            raise ApiError(422, "INVALID_CALCULATOR_EXPRESSION", "calculator result must be numeric")
        return result


native_tools = NativeToolRegistry()
