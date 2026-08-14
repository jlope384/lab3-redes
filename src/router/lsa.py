"""Construccion y flooding de LSAs (Link State Advertisement).

Formato acordado:
{ "type": "LSA", "origin": <id>, "seq": <int>, "ttl": <int>,
  "links": {"<vecino>": <costo>, ...}, "from": <id> }

`seq` se deriva de un timestamp en ms (en vez de reiniciar en 0 en memoria):
si el proceso se reinicia, el `seq` del siguiente LSA sigue siendo mayor que
el ultimo que los demas nodos ya conocian para este origen, asi que no se
descarta como "viejo". Se fuerza estrictamente creciente por si dos floods
caen en el mismo milisegundo.
"""
from __future__ import annotations

import json
import threading
import time
from typing import Callable

from src.transport.sockets import control_port, send_line

DEFAULT_TTL = 16


class LSAManager:
    def __init__(
        self,
        self_id: str,
        addressbook: dict,
        live_links_provider: Callable[[], dict],
        on_lsa: Callable[[dict], None] | None = None,
    ) -> None:
        self.self_id = self_id
        self.addressbook = addressbook
        self.live_links_provider = live_links_provider  # -> {vecino_id: costo} vivos ahora mismo
        self.on_lsa = on_lsa  # callback(lsa) para alimentar el grafo local
        self._last_seq_seen: dict[str, int] = {}
        self._own_last_seq = 0
        self._lock = threading.Lock()

    def _next_seq(self) -> int:
        with self._lock:
            candidate = int(time.time() * 1000)
            self._own_last_seq = max(candidate, self._own_last_seq + 1)
            return self._own_last_seq

    def build_own_lsa(self, ttl: int = DEFAULT_TTL) -> dict:
        return {
            "type": "LSA",
            "origin": self.self_id,
            "seq": self._next_seq(),
            "ttl": ttl,
            "links": self.live_links_provider(),
            "from": self.self_id,
        }

    def flood_own_lsa(self) -> None:
        lsa = self.build_own_lsa()
        self._remember(lsa["origin"], lsa["seq"])
        self._broadcast(lsa, exclude=None)
        if self.on_lsa:
            self.on_lsa(lsa)

    def handle_incoming(self, lsa: dict) -> None:
        """Descarta duplicados/viejos por `seq`; si es nuevo, aprende y reenvia."""
        origin = lsa["origin"]
        seq = lsa["seq"]
        ttl = lsa.get("ttl", 0)

        with self._lock:
            if seq <= self._last_seq_seen.get(origin, -1):
                return  # duplicado o desactualizado -> se descarta (evita loops)
            self._last_seq_seen[origin] = seq

        if self.on_lsa:
            self.on_lsa(lsa)

        if ttl <= 0:
            return  # limite de propagacion alcanzado

        forwarded = dict(lsa)
        forwarded["ttl"] = ttl - 1
        forwarded["from"] = self.self_id
        self._broadcast(forwarded, exclude=lsa.get("from"))

    def _remember(self, origin: str, seq: int) -> None:
        with self._lock:
            self._last_seq_seen[origin] = seq

    def _broadcast(self, lsa: dict, exclude: str | None) -> None:
        line = json.dumps(lsa)
        for neighbor_id in self.live_links_provider():
            if neighbor_id == exclude:
                continue
            addr = self.addressbook.get(neighbor_id)
            if not addr:
                continue
            try:
                send_line(addr["ip"], control_port(addr["port"]), line)
            except OSError:
                pass  # vecino caido/no disponible
