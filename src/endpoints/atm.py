"""Cliente ATM de prueba: se conecta a su router gateway y envia operaciones
bancarias usando el JSON {type, origin, destination, payload} del protocolo
acordado.

Uso: python -m src.endpoints.atm <self_id> <gateway_id> <banco_id> [--usuario U] [--pin P]
"""
from __future__ import annotations

import argparse
import json
import os
import queue

from src.dataplane.banking import auth, logout, withdraw
from src.linklayer.framing import bits_to_text, decode_frame, encode_frame, text_to_bits
from src.transport.sockets import send_line, start_line_server

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RESPUESTA_TIMEOUT = 5.0


def load_addressbook() -> dict:
    with open(os.path.join(os.path.dirname(BASE_DIR), "config", "nodos.json")) as f:
        return {k: v for k, v in json.load(f).items() if not k.startswith("_")}


def send_message(ip: str, port: int, message: dict) -> None:
    bits = text_to_bits(json.dumps(message))
    send_line(ip, port, encode_frame(bits))


def main() -> None:
    parser = argparse.ArgumentParser(description="Cliente ATM de prueba (Lab 3).")
    parser.add_argument("self_id", help="Id de este ATM en config/nodos.json")
    parser.add_argument("gateway_id", help="Id del router gateway en config/nodos.json")
    parser.add_argument("banco_id", help="Id del servidor bancario (destino final)")
    parser.add_argument("--usuario", help="Usuario a autenticar (si no se da, se pregunta por consola)")
    parser.add_argument("--pin", help="PIN del usuario (si no se da, se pregunta por consola)")
    args = parser.parse_args()

    addressbook = load_addressbook()
    for required in (args.self_id, args.gateway_id):
        if required not in addressbook:
            raise SystemExit(f"'{required}' no existe en config/nodos.json")

    self_addr = addressbook[args.self_id]
    gateway = addressbook[args.gateway_id]

    inbox: "queue.Queue[dict]" = queue.Queue()

    def on_response(raw_frame: str, _addr) -> None:
        try:
            data_bits = decode_frame(raw_frame)
            message = json.loads(bits_to_text(data_bits))
        except (ValueError, UnicodeDecodeError):
            return  # frame corrupto, se descarta
        inbox.put(message)

    start_line_server(self_addr["ip"], self_addr["port"], on_response)

    def enviar_y_esperar(mensaje: dict) -> dict | None:
        try:
            send_message(gateway["ip"], gateway["port"], mensaje)
        except OSError as exc:
            print(
                f"[{args.self_id}] no se pudo conectar al gateway '{args.gateway_id}' "
                f"({gateway['ip']}:{gateway['port']}): {exc}. "
                f"¿Ya corriste `python -m src.node {args.gateway_id}`?"
            )
            return None
        try:
            return inbox.get(timeout=RESPUESTA_TIMEOUT)
        except queue.Empty:
            print(
                f"[{args.self_id}] no hubo respuesta en {RESPUESTA_TIMEOUT}s. Revisa que todos los "
                f"routers entre '{args.gateway_id}' y '{args.banco_id}' esten corriendo y que "
                f"config/endpoints.json tenga a '{args.banco_id}'."
            )
            return None

    print(f"=== ATM {args.self_id} (gateway {args.gateway_id} -> banco {args.banco_id}) ===")
    usuario = args.usuario or input("Usuario: ").strip()
    pin = args.pin or input("PIN: ").strip()

    respuesta = enviar_y_esperar(auth(args.self_id, args.banco_id, usuario, pin))
    if respuesta is None:
        return

    payload = respuesta.get("payload", {})
    if payload.get("status") != "ok":
        print(f"[{args.self_id}] login rechazado: {payload.get('message', 'sin detalle')}")
        return

    print(f"[{args.self_id}] sesion iniciada como '{usuario}'. Saldo actual: {payload.get('saldo')}")

    while True:
        print("\n1) Retirar\n2) Cerrar sesion")
        opcion = input("Elige una opcion: ").strip()

        if opcion == "1":
            try:
                monto = float(input("Monto a retirar: ").strip())
            except ValueError:
                print("Monto invalido.")
                continue

            respuesta = enviar_y_esperar(withdraw(args.self_id, args.banco_id, usuario, monto))
            if respuesta is None:
                continue
            payload = respuesta.get("payload", {})
            if payload.get("status") == "ok":
                print(f"[{args.self_id}] retiro exitoso. Nuevo saldo: {payload.get('saldo')}")
            else:
                print(f"[{args.self_id}] retiro rechazado: {payload.get('message', 'sin detalle')}")

        elif opcion == "2":
            enviar_y_esperar(logout(args.self_id, args.banco_id))
            print(f"[{args.self_id}] sesion cerrada.")
            break

        else:
            print("Opcion invalida.")


if __name__ == "__main__":
    main()
