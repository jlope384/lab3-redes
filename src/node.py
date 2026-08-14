"""Entry point de un nodo router: corre HELLO, LSA/flooding, Dijkstra y
forwarding en paralelo.

Uso: python -m src.node <node_id>
"""
from __future__ import annotations

import argparse
import json
import os
import threading
import time

from src.dataplane.forwarding import ForwardingLayer, RoutingTable, write_routing_table
from src.router.hello import HelloManager
from src.router.lsa import LSAManager
from src.router.network_graph import NetworkGraph
from src.router.routing import compute_routes
from src.transport.sockets import start_line_server

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LSA_REFRESH_INTERVAL = 15.0  # re-flood periodico aunque nada haya cambiado


def load_config(node_id: str):
    def _load(name: str) -> dict:
        path = os.path.join(BASE_DIR, "config", name)
        if not os.path.exists(path):
            return {}
        with open(path) as f:
            return {k: v for k, v in json.load(f).items() if not k.startswith("_")}

    addressbook = _load("nodos.json")
    topologia = _load("topologia.json")
    endpoints = _load("endpoints.json")
    return addressbook, topologia.get(node_id, {}), endpoints


def main() -> None:
    parser = argparse.ArgumentParser(description="Levanta un nodo router del Lab 3.")
    parser.add_argument("node_id", help="Identificador del nodo (debe existir en config/nodos.json)")
    args = parser.parse_args()

    node_id = args.node_id
    addressbook, configured_neighbors, endpoints = load_config(node_id)
    if node_id not in addressbook:
        raise SystemExit(f"'{node_id}' no existe en config/nodos.json")
    self_addr = addressbook[node_id]
    csv_path = os.path.join(BASE_DIR, "data", f"nodo_{node_id}_tabla_enrutamiento.csv")

    graph = NetworkGraph()
    table = RoutingTable(csv_path)

    # Bootstrap optimista: hasta que HELLO confirme vecinos vivos, se asume la
    # topologia configurada para poder calcular rutas desde el arranque.
    graph.update_from_lsa(node_id, configured_neighbors)

    def recompute_routes() -> None:
        routes = compute_routes(graph.snapshot(), node_id)
        write_routing_table(csv_path, routes, addressbook)
        table.reload()
        print(f"[{node_id}] tabla actualizada: {routes}", flush=True)

    def on_lsa_learned(lsa: dict) -> None:
        graph.update_from_lsa(lsa["origin"], lsa.get("links", {}))
        recompute_routes()

    lsa_manager = LSAManager(
        node_id, addressbook, live_links_provider=lambda: hello_manager.live_neighbors(), on_lsa=on_lsa_learned
    )

    def on_link_change(neighbor_id: str, is_up: bool) -> None:
        print(f"[{node_id}] enlace con {neighbor_id}: {'UP' if is_up else 'DOWN'}", flush=True)
        lsa_manager.flood_own_lsa()  # tanto UP como DOWN cambian mis links -> hay que re-anunciar

    hello_manager = HelloManager(node_id, configured_neighbors, addressbook, on_link_change=on_link_change)

    def on_local_deliver(message: dict) -> None:
        print(f"[{node_id}] mensaje entregado localmente a {message.get('destination')}: {message}", flush=True)

    forwarding = ForwardingLayer(node_id, table, addressbook, endpoints, on_local_deliver)

    def on_incoming_line(raw_line: str, addr: tuple) -> None:
        # Un solo puerto por nodo para todo (control y datos, asi lo esperan
        # las otras 2 parejas): un frame de datos ya paso por Hamming(7,4),
        # asi que solo tiene '0'/'1'; un mensaje de control (HELLO/LSA)
        # siempre es JSON y empieza con '{'.
        if raw_line and raw_line[0] in "01":
            forwarding.handle_frame(raw_line, addr)
            return

        try:
            message = json.loads(raw_line)
        except ValueError:
            print(f"[{node_id}] linea invalida descartada: {raw_line!r}", flush=True)
            return

        msg_type = message.get("type")
        if msg_type == "HELLO":
            hello_manager.handle_hello(message)
        elif msg_type == "LSA":
            lsa_manager.handle_incoming(message)
        else:
            print(f"[{node_id}] tipo de paquete de control desconocido ignorado: {msg_type!r}", flush=True)

    start_line_server(self_addr["ip"], self_addr["port"], on_incoming_line)
    hello_manager.start()

    def _lsa_refresh_loop() -> None:
        # Re-manda el LSA propio periodicamente, no solo cuando cambia un
        # enlace: cubre el caso en que un vecino todavia no escuchaba cuando
        # se mando el primer flood, o un nodo se reinicio y su vecino nunca
        # detecto el enlace caido (timeout de HELLO).
        while True:
            time.sleep(LSA_REFRESH_INTERVAL)
            lsa_manager.flood_own_lsa()

    threading.Thread(target=_lsa_refresh_loop, daemon=True).start()

    recompute_routes()
    lsa_manager.flood_own_lsa()

    print(
        f"[{node_id}] escuchando en {self_addr['ip']}:{self_addr['port']} (control + datos)",
        flush=True,
    )

    while True:
        time.sleep(1)


if __name__ == "__main__":
    main()
