import signal
from typing import Any

from RestrictedPython import compile_restricted, safe_builtins
from RestrictedPython.Eval import default_guarded_getitem
from RestrictedPython.Guards import (
    guarded_iter_unpack_sequence,
    guarded_unpack_sequence,
    safer_getattr,
)

from .proxy import RadarProxy

_TIMEOUT_SECONDS = 5

_READ_METHODS = {
    "list_technologies",
    "list_teams",
    "list_assignments",
    "get_assignment",
    "is_dirty",
}


class _ReadOnlyRadar:
    """Wraps a RadarProxy and exposes read methods only."""

    def __init__(self, proxy: RadarProxy) -> None:
        self._proxy = proxy

    def __getattr__(self, name: str) -> Any:
        if name in _READ_METHODS:
            return getattr(self._proxy, name)
        raise ValueError(
            f"search is read-only. '{name}' is not available. "
            "Use execute() to make changes."
        )


def _make_globals(radar_obj: Any) -> dict[str, Any]:
    builtins = dict(safe_builtins)
    # allow common harmless helpers the model may use
    for k in ("len", "range", "min", "max", "sum", "sorted", "any", "all",
              "enumerate", "zip", "map", "filter", "list", "dict", "set",
              "tuple", "str", "int", "float", "bool", "abs", "round", "print"):
        if k in __builtins__ if isinstance(__builtins__, dict) else hasattr(__builtins__, k):  # type: ignore
            try:
                builtins[k] = (__builtins__[k] if isinstance(__builtins__, dict)  # type: ignore
                               else getattr(__builtins__, k))
            except Exception:
                pass
    return {
        "__builtins__": builtins,
        "_getattr_": safer_getattr,
        "_getitem_": default_guarded_getitem,
        "_unpack_sequence_": guarded_unpack_sequence,
        "_iter_unpack_sequence_": guarded_iter_unpack_sequence,
        "_getiter_": iter,
        "radar": radar_obj,
    }


def _timeout_handler(signum: int, frame: Any) -> None:
    raise TimeoutError(f"Sandbox execution exceeded {_TIMEOUT_SECONDS}s")


def _run(code: str, glb: dict[str, Any]) -> Any:
    try:
        byte_code = compile_restricted(code, "<sandbox>", "exec")
    except SyntaxError as e:
        raise ValueError(f"Syntax error in sandbox code: {e}") from e

    old_handler = None
    try:
        if hasattr(signal, "SIGALRM"):
            old_handler = signal.signal(signal.SIGALRM, _timeout_handler)
            signal.alarm(_TIMEOUT_SECONDS)
        local_ns: dict[str, Any] = {}
        try:
            exec(byte_code, glb, local_ns)
        except ValueError:
            raise
        except Exception as e:
            raise ValueError(str(e)) from e
        if "result" in local_ns:
            return local_ns["result"]
        return None
    finally:
        if hasattr(signal, "SIGALRM"):
            signal.alarm(0)
            if old_handler is not None:
                signal.signal(signal.SIGALRM, old_handler)


def run_search(code: str, radar_instance: RadarProxy) -> Any:
    glb = _make_globals(_ReadOnlyRadar(radar_instance))
    return _run(code, glb)


def run_execute(code: str) -> Any:
    proxy = RadarProxy()
    glb = _make_globals(proxy)
    result = _run(code, glb)
    if proxy.is_dirty:
        proxy.commit("auto-commit after execute()")
    return result
