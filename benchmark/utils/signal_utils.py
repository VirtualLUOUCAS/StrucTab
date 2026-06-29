"""Global abort signal: the first Ctrl+C sets a flag for a graceful shutdown,
the second one exits immediately.
"""

from __future__ import annotations

import os
import signal
import threading

ABORT_EVENT = threading.Event()
_INSTALLED = False
_SIGINT_COUNT = 0


def _handler(signum, frame):
    global _SIGINT_COUNT
    _SIGINT_COUNT += 1
    ABORT_EVENT.set()
    msg = (
        "\n[abort] Ctrl+C received, asking the main loop to exit and flush; press Ctrl+C again to force quit...\n"
        if _SIGINT_COUNT == 1
        else "\n[abort] Ctrl+C received again, forcing exit now (recently unflushed data may be lost).\n"
    )
    try:
        os.write(2, msg.encode("utf-8", errors="replace"))
    except Exception:
        pass
    if _SIGINT_COUNT >= 2:
        os._exit(130)


def install_signal_handlers_once() -> None:
    global _INSTALLED
    if _INSTALLED:
        return
    try:
        signal.signal(signal.SIGINT, _handler)
        signal.signal(signal.SIGTERM, _handler)
    except Exception:
        pass
    _INSTALLED = True
