"""Utilidades TCP compartidas por routers, ATM y banco.

Protocolo de transporte acordado: TCP, un mensaje por linea terminada en
'\n', sin prefijo de longitud. Cada envio abre una conexion corta, manda la
linea y cierra (no hay conexion persistente entre vecinos).

- Plano de control (HELLO/LSA): la linea es JSON plano.
- Plano de datos: la linea es una cadena de bits ('0'/'1') ya codificada con
  Hamming(7,4).
"""
from __future__ import annotations

import socket
import threading
from typing import Callable

BUFFER_SIZE = 4096
ENCODING = "utf-8"
CONTROL_PORT_OFFSET = 1000  # puerto de control = puerto de datos + este offset


def control_port(data_port: int) -> int:
    return data_port + CONTROL_PORT_OFFSET


def send_line(ip: str, port: int, text: str, timeout: float = 3.0) -> None:
    """Abre una conexion TCP corta, envia una linea y cierra."""
    with socket.create_connection((ip, port), timeout=timeout) as sock:
        sock.sendall((text + "\n").encode(ENCODING))


def recv_line(conn: socket.socket) -> str | None:
    """Lee de un socket ya conectado hasta encontrar '\n' (o EOF)."""
    chunks = []
    while True:
        chunk = conn.recv(BUFFER_SIZE)
        if not chunk:
            break
        chunks.append(chunk)
        if chunk.endswith(b"\n"):
            break
    if not chunks:
        return None
    return b"".join(chunks).decode(ENCODING).strip()


def start_line_server(ip: str, port: int, on_line: Callable[[str, tuple], None], backlog: int = 20) -> socket.socket:
    """Levanta un servidor TCP (hilo daemon) que invoca on_line(texto, addr) por conexion.

    Cada conexion se atiende en su propio hilo daemon: si un peer manda datos
    corruptos, se queda a medias o `on_line` truena, el resto de conexiones
    (y el nodo entero) no se ve afectado.
    """
    server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    server.bind((ip, port))
    server.listen(backlog)

    def _handle(conn: socket.socket, addr: tuple) -> None:
        try:
            with conn:
                line = recv_line(conn)
                if line is not None:
                    on_line(line, addr)
        except Exception as exc:  # noqa: BLE001 - un peer malicioso/roto no debe tumbar el nodo
            print(f"[sockets] conexion de {addr} descartada: {exc!r}", flush=True)

    def _accept_loop() -> None:
        while True:
            try:
                conn, addr = server.accept()
            except OSError:
                return  # socket cerrado (shutdown del proceso)
            threading.Thread(target=_handle, args=(conn, addr), daemon=True).start()

    threading.Thread(target=_accept_loop, daemon=True).start()
    return server
