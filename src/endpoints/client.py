"""Nodo cliente ATM (Lab 3): se conecta a su router gateway y envia operaciones
bancarias usando el JSON {type, origin, destination, payload} del protocolo
acordado con las otras parejas (ver Lab 3 Protocolo Proposal.pdf).

Flujo: se autentica una vez (AUTH); si el banco acepta, se queda "conectado"
(en realidad: sigue en el mismo proceso, escuchando respuestas del banco por
su propio socket) y muestra un menu para hacer retiros. Al elegir "cerrar
sesion" manda LOGOUT y termina el programa (deja de escuchar).

No confundir con Extras/server.py, que es la demo de capas del Lab 2
(login/withdraw/logout con framing propio) usada como referencia.

Uso: python -m src.endpoints.client <self_id> <gateway_id> <bank_id> [--user U] [--pin P]
"""
from __future__ import annotations

import argparse
import json
import os
import queue

from src.dataplane.banking import auth, logout, withdraw
from src.linklayer.framing import bits_to_text, text_to_bits
from src.linklayer.framing import decode_frame as hamming_decode
from src.linklayer.framing import encode_frame as hamming_encode
from src.transport.sockets import send_line, start_line_server

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RESPUESTA_TIMEOUT = 5.0


def load_addressbook() -> dict:
    with open(os.path.join(os.path.dirname(BASE_DIR), "config", "nodos.json")) as f:
        return {k: v for k, v in json.load(f).items() if not k.startswith("_")}


def send_message(gateway_ip: str, gateway_port: int, message: dict) -> None:
    bits = text_to_bits(json.dumps(message))
    encoded = hamming_encode(bits)
    send_line(gateway_ip, gateway_port, encoded)


def main() -> None:
    parser = argparse.ArgumentParser(description="Cliente ATM de prueba (Lab 3).")
    parser.add_argument("self_id", help="Id de este ATM en config/nodos.json")
    parser.add_argument("gateway_id", help="Id del router gateway en config/nodos.json")
    parser.add_argument("bank_id", help="Id del servidor bancario (destino final)")
    parser.add_argument("--user", help="Usuario a autenticar (si no se da, se pregunta por consola)")
    parser.add_argument("--pin", help="PIN del usuario a autenticar (si no se da, se pregunta por consola)")
    args = parser.parse_args()

    addressbook = load_addressbook()
    if args.self_id not in addressbook:
        raise SystemExit(f"'{args.self_id}' no existe en config/nodos.json")
    if args.gateway_id not in addressbook:
        raise SystemExit(f"'{args.gateway_id}' no existe en config/nodos.json")

    self_addr = addressbook[args.self_id]
    gateway = addressbook[args.gateway_id]

    # Cola donde el listener de respuestas deja cada mensaje que llega del banco.
    inbox: "queue.Queue[dict]" = queue.Queue()

    def on_response(raw_bits: str, _addr) -> None:
        try:
            data_bits = hamming_decode(raw_bits)
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
                f"[{args.self_id}] no hubo respuesta en {RESPUESTA_TIMEOUT}s. "
                f"Revisa que todos los routers entre '{args.gateway_id}' y '{args.bank_id}' "
                f"esten corriendo (y que config/endpoints.json tenga a '{args.bank_id}')."
            )
            return None

    print(f"=== ATM {args.self_id} (gateway {args.gateway_id} -> banco {args.bank_id}) ===")
    user = args.user or input("Usuario: ").strip()
    pin = args.pin or input("PIN: ").strip()

    respuesta = enviar_y_esperar(auth(args.self_id, args.bank_id, user, pin))
    if respuesta is None:
        return

    payload = respuesta.get("payload", {})
    if payload.get("status") != "ok":
        print(f"[{args.self_id}] login rechazado: {payload.get('message', 'sin detalle')}")
        return

    print(f"[{args.self_id}] sesion iniciada como '{user}'. Saldo actual: {payload.get('saldo')}")

    while True:
        print("\n1) Retirar\n2) Cerrar sesion")
        opcion = input("Elige una opcion: ").strip()

        if opcion == "1":
            monto_str = input("Monto a retirar: ").strip()
            try:
                monto = float(monto_str)
            except ValueError:
                print("Monto invalido.")
                continue

            respuesta = enviar_y_esperar(withdraw(args.self_id, args.bank_id, user, monto))
            if respuesta is None:
                continue
            payload = respuesta.get("payload", {})
            if payload.get("status") == "ok":
                print(f"[{args.self_id}] retiro exitoso. Nuevo saldo: {payload.get('saldo')}")
            else:
                print(f"[{args.self_id}] retiro rechazado: {payload.get('message', 'sin detalle')}")

        elif opcion == "2":
            enviar_y_esperar(logout(args.self_id, args.bank_id))
            print(f"[{args.self_id}] sesion cerrada.")
            break

        else:
            print("Opcion invalida.")


main()
