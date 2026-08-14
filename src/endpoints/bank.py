"""Servidor bancario de prueba: escucha en su router gateway y responde
operaciones AUTH/WITHDRAW/LOGOUT segun el protocolo acordado.

Uso: python -m src.endpoints.bank <self_id> <gateway_id>
"""
from __future__ import annotations

import argparse
import json
import os
import time

from src.dataplane.banking import handle_incoming
from src.linklayer.framing import bits_to_text, decode_frame, encode_frame, text_to_bits
from src.transport.sockets import send_line, start_line_server

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def load_addressbook() -> dict:
    with open(os.path.join(os.path.dirname(BASE_DIR), "config", "nodos.json")) as f:
        return {k: v for k, v in json.load(f).items() if not k.startswith("_")}


def main() -> None:
    parser = argparse.ArgumentParser(description="Servidor bancario de prueba (Lab 3).")
    parser.add_argument("self_id", help="Id de este banco en config/nodos.json")
    parser.add_argument("gateway_id", help="Id del router gateway en config/nodos.json")
    args = parser.parse_args()

    addressbook = load_addressbook()
    for required in (args.self_id, args.gateway_id):
        if required not in addressbook:
            raise SystemExit(f"'{required}' no existe en config/nodos.json")

    self_addr = addressbook[args.self_id]
    gateway = addressbook[args.gateway_id]

    def on_frame(raw_frame: str, _addr) -> None:
        try:
            data_bits = decode_frame(raw_frame)
            message = json.loads(bits_to_text(data_bits))
        except (ValueError, UnicodeDecodeError):
            return  # frame corrupto, se descarta
        print(f"[{args.self_id}] recibido: {message}", flush=True)

        response = handle_incoming(message)
        frame = encode_frame(text_to_bits(json.dumps(response)))
        try:
            send_line(gateway["ip"], gateway["port"], frame)
        except OSError as exc:
            print(f"[{args.self_id}] no se pudo responder via gateway '{args.gateway_id}': {exc}", flush=True)

    start_line_server(self_addr["ip"], self_addr["port"], on_frame)
    print(f"[{args.self_id}] escuchando en {self_addr['ip']}:{self_addr['port']}", flush=True)

    while True:
        time.sleep(1)


if __name__ == "__main__":
    main()
