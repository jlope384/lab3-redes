"""Capa de red del plano de datos: recibe bits, corrige errores (Hamming 7,4),
consulta la tabla de ruteo y reenvia al siguiente salto (o entrega local si el
destino es un endpoint propio).
"""
from __future__ import annotations

import csv
import json
import threading
from typing import Callable

from src.linklayer.framing import bits_to_text, decode_frame, encode_frame, text_to_bits
from src.transport.sockets import send_line


class RoutingTable:
    """Envuelve el CSV de ruteo: destino -> siguiente_salto/ip/puerto/costo."""

    def __init__(self, csv_path: str) -> None:
        self.csv_path = csv_path
        self._rows: dict[str, dict] = {}
        self._lock = threading.Lock()
        self.reload()

    def reload(self) -> None:
        rows: dict[str, dict] = {}
        try:
            with open(self.csv_path, newline="") as f:
                for row in csv.DictReader(f):
                    rows[row["destino"]] = {
                        "siguiente_salto": row["siguiente_salto"],
                        "ip": row["ip"],
                        "puerto": int(row["puerto"]),
                        "costo": float(row.get("costo", 0)),
                    }
        except FileNotFoundError:
            pass  # aun no se calculo la primera tabla
        with self._lock:
            self._rows = rows

    def lookup(self, destino: str) -> dict | None:
        with self._lock:
            return self._rows.get(destino)


def write_routing_table(csv_path: str, routes: dict, addressbook: dict) -> None:
    """routes: {destino: (costo, siguiente_salto)}."""
    with open(csv_path, "w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["destino", "siguiente_salto", "ip", "puerto", "costo"])
        for dest, (costo, next_hop) in routes.items():
            addr = addressbook.get(next_hop, {})
            writer.writerow([dest, next_hop, addr.get("ip", ""), addr.get("port", ""), costo])


class ForwardingLayer:
    """Escucha frames de datos entrantes y los reenvia hacia su destino final.

    `destination` en un mensaje de datos es un ATM/servidor (endpoint), no un
    router. `endpoints` resuelve {endpoint_id: id_del_router_gateway}:
    - Si el gateway de ese endpoint soy yo -> entrego directo por socket
      usando la ip/puerto real del endpoint (en `addressbook`).
    - Si el gateway es otro router -> reenvio el mensaje intacto hacia ese
      router siguiendo la tabla de ruteo normal.
    """

    def __init__(
        self,
        self_id: str,
        table: RoutingTable,
        addressbook: dict,
        endpoints: dict | None = None,
        on_local_deliver: Callable[[dict], None] | None = None,
    ) -> None:
        self.self_id = self_id
        self.table = table
        self.addressbook = addressbook
        self.endpoints = endpoints or {}
        self.on_local_deliver = on_local_deliver

    def handle_frame(self, raw_frame: str, _addr) -> None:
        try:
            data_bits = decode_frame(raw_frame)
            message = json.loads(bits_to_text(data_bits))
        except (ValueError, UnicodeDecodeError):
            return  # frame corrupto mas alla de lo que Hamming(7,4) puede corregir
        self.forward(message)

    def forward(self, message: dict) -> None:
        destino = message.get("destination")
        gateway_id = self.endpoints.get(destino)

        # `destino` es un endpoint conocido cuyo gateway soy yo -> entrega directa.
        if gateway_id == self.self_id:
            self._deliver_to_endpoint(message, destino)
            return

        # Si es un endpoint con otro gateway, el "objetivo" a alcanzar por la
        # tabla de ruteo es ese gateway; si no es un endpoint conocido, se
        # asume que `destino` ya es un id de router.
        target = gateway_id or destino

        if target == self.self_id:
            if self.on_local_deliver:
                self.on_local_deliver(message)
            return

        route = self.table.lookup(target)
        if not route:
            return  # sin ruta conocida todavia
        print(
            f"[{self.self_id}] reenviando datagrama {message.get('origin')} -> "
            f"{message.get('destination')} via {route['siguiente_salto']}",
            flush=True,
        )
        self._send(message, route["ip"], route["puerto"])

    def _deliver_to_endpoint(self, message: dict, destino: str) -> None:
        addr = self.addressbook.get(destino)
        if not addr:
            return  # el endpoint no tiene ip/puerto registrado en nodos.json
        self._send(message, addr["ip"], addr["port"])
        if self.on_local_deliver:
            self.on_local_deliver(message)

    @staticmethod
    def _send(message: dict, ip: str, port: int) -> None:
        bits = text_to_bits(json.dumps(message))
        frame = encode_frame(bits)
        try:
            send_line(ip, port, frame)
        except OSError:
            pass  # destino/siguiente salto no disponible
