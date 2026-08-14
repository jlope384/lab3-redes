"""Descubrimiento/monitoreo de vecinos vivos via paquetes HELLO periodicos.

Formato acordado: {"type": "HELLO", "from": "<self_id>"} — unidireccional,
sin ACK. Cada nodo manda su propio HELLO cada `interval` segundos a cada
vecino configurado; recibir el HELLO del vecino (en cualquier direccion) es
lo que cuenta como "el enlace esta vivo". Si no se ve un HELLO del vecino en
`timeout` segundos, se marca DOWN.
"""
from __future__ import annotations

import json
import threading
import time
from typing import Callable

from src.transport.sockets import send_line

DEFAULT_INTERVAL = 2.0
DEFAULT_TIMEOUT = 6.0


class HelloManager:
    def __init__(
        self,
        self_id: str,
        configured_neighbors: dict,
        addressbook: dict,
        interval: float = DEFAULT_INTERVAL,
        timeout: float = DEFAULT_TIMEOUT,
        on_link_change: Callable[[str, bool], None] | None = None,
    ) -> None:
        self.self_id = self_id
        self.configured_neighbors = configured_neighbors  # {vecino_id: costo}, fuente de verdad estatica
        self.addressbook = addressbook
        self.interval = interval
        self.timeout = timeout
        self.on_link_change = on_link_change
        self._last_seen: dict[str, float] = {n: 0.0 for n in configured_neighbors}
        self._is_up: dict[str, bool] = {n: False for n in configured_neighbors}
        self._lock = threading.Lock()

    def start(self) -> None:
        threading.Thread(target=self._send_loop, daemon=True).start()
        threading.Thread(target=self._watchdog_loop, daemon=True).start()

    def live_neighbors(self) -> dict:
        """Subconjunto de `configured_neighbors` cuyo enlace esta actualmente UP."""
        with self._lock:
            return {n: cost for n, cost in self.configured_neighbors.items() if self._is_up.get(n)}

    def handle_hello(self, message: dict) -> None:
        sender = message.get("from")
        if sender not in self.configured_neighbors:
            return
        became_up = False
        with self._lock:
            self._last_seen[sender] = time.time()
            if not self._is_up.get(sender, False):
                self._is_up[sender] = True
                became_up = True
        if became_up and self.on_link_change:
            self.on_link_change(sender, True)

    def _send_loop(self) -> None:
        hello_line = json.dumps({"type": "HELLO", "from": self.self_id})
        while True:
            for neighbor_id in self.configured_neighbors:
                addr = self.addressbook.get(neighbor_id)
                if not addr:
                    continue
                try:
                    send_line(addr["ip"], addr["port"], hello_line)
                except OSError:
                    pass  # vecino caido/no disponible todavia; el watchdog lo marcara DOWN
            time.sleep(self.interval)

    def _watchdog_loop(self) -> None:
        while True:
            time.sleep(self.interval)
            now = time.time()
            newly_down = []
            with self._lock:
                for neighbor_id, last_seen in self._last_seen.items():
                    if self._is_up.get(neighbor_id) and last_seen and now - last_seen > self.timeout:
                        self._is_up[neighbor_id] = False
                        newly_down.append(neighbor_id)
            for neighbor_id in newly_down:
                if self.on_link_change:
                    self.on_link_change(neighbor_id, False)
