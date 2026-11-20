"""Domain event sederhana (sinkron, dalam satu proses).

Konteks hilir hanya bereaksi pada isi event, bukan membaca tabel konteks hulu,
sehingga tiap modul dapat dipindah menjadi service sendiri tanpa mengubah modelnya.
Setiap event juga menaikkan meta.seq karena menandakan perubahan data.
"""
from collections import defaultdict
from typing import Callable

from .meta import bump_seq

_handlers: dict[str, list[Callable]] = defaultdict(list)


def subscribe(event: str, handler: Callable) -> None:
    if handler not in _handlers[event]:
        _handlers[event].append(handler)


def publish(event: str, conn, **payload) -> None:
    bump_seq(conn)
    for handler in _handlers[event]:
        handler(conn, payload)