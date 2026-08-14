"""Rutas mas cortas (Dijkstra) sobre el grafo construido a partir de los LSA."""
from __future__ import annotations

import heapq


def compute_routes(graph: dict, source: str) -> dict:
    """graph: {nodo: {vecino: costo}}. Devuelve {destino: (costo, siguiente_salto)}."""
    best_cost = {source: 0.0}
    came_from: dict[str, str] = {}
    settled = set()
    frontier = [(0.0, source)]

    while frontier:
        cost, node = heapq.heappop(frontier)
        if node in settled:
            continue
        settled.add(node)

        for neighbor, edge_cost in graph.get(node, {}).items():
            candidate = cost + edge_cost
            if candidate < best_cost.get(neighbor, float("inf")):
                best_cost[neighbor] = candidate
                came_from[neighbor] = node
                heapq.heappush(frontier, (candidate, neighbor))

    routes = {}
    for dest, cost in best_cost.items():
        if dest == source:
            continue
        first_hop = _first_hop(came_from, source, dest)
        if first_hop is not None:
            routes[dest] = (cost, first_hop)
    return routes


def _first_hop(came_from: dict, source: str, dest: str) -> str | None:
    node = dest
    while came_from.get(node) != source:
        node = came_from.get(node)
        if node is None:
            return None
    return node
