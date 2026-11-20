"""Domain event sederhana (sinkron, dalam satu proses).

Konteks hilir hanya bereaksi pada isi event, bukan membaca tabel konteks hulu,
sehingga tiap modul dapat dipindah menjadi service sendiri tanpa mengubah modelnya.
"""
from collections import defaultdict
from typing import Callable

_handlers: dict[str, list[Callable]] = defaultdict(list)


def subscribe(event: str, handler: Callable) -> None:
    if handler not in _handlers[event]:
        _handlers[event].append(handler)


def publish(event: str, conn, **payload) -> None:
    for handler in _handlers[event]:
        handler(conn, payload)
