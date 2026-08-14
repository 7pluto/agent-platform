import asyncio

from app.core.errors import ApiError
from app.runtime.native_tools import native_tools


def test_native_tools_are_whitelisted_and_safe() -> None:
    async def run() -> None:
        assert (await native_tools.invoke("calculator", {"expression": "2 * (3 + 4)"}))["value"] == 14
        assert (await native_tools.invoke("echo", {"value": "hello"}))["value"] == "hello"
        try:
            await native_tools.invoke("calculator", {"expression": "__import__('os').system('whoami')"})
        except ApiError as exc:
            assert exc.code == "INVALID_CALCULATOR_EXPRESSION"
        else:
            raise AssertionError("calculator evaluated arbitrary code")

    asyncio.run(run())


def test_calculator_rejects_nonfinite_results() -> None:
    async def run() -> None:
        try:
            await native_tools.invoke("calculator", {"expression": "1 / 0"})
        except ZeroDivisionError:
            pass
        else:
            raise AssertionError("expected arithmetic error")

    asyncio.run(run())
