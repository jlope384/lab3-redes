"""Grafo de la red, reconstruido a partir de los LSA recibidos de cada origen."""
from __future__ import annotations

import threading


class NetworkGraph:
    def __init__(self) -> None:
        self._adjacency: dict[str, dict[str, float]] = {}
        self._lock = threading.Lock()

    def update_from_lsa(self, origin: str, links: dict) -> None:
        """Reemplaza por completo las adyacencias conocidas de `origin`.

        Un LSA nuevo del mismo origen siempre refleja su estado actual de
        enlaces (incluye el caso de un enlace que se cayo: simplemente ya no
        aparece en `links`), asi que reemplazar en vez de mezclar es correcto.
        """
        with self._lock:
            self._adjacency[origin] = dict(links)

    def snapshot(self) -> dict:
        with self._lock:
            return {node: dict(neighbors) for node, neighbors in self._adjacency.items()}
