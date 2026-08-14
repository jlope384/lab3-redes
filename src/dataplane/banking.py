"""Payloads de operaciones bancarias (ATM <-> Banco) y logica de sesion del
lado servidor. `auth`/`withdraw`/`logout`/`error` arman el JSON; el servidor
usa `handle_incoming` para validar y responder con el mismo `type`.
"""
from __future__ import annotations

import json
import os

from src.dataplane.messages import build_message

BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
_BANKING_DATA_PATH = os.path.join(BASE_DIR, "data", "banking_data.json")

with open(_BANKING_DATA_PATH, "r") as _f:
    _BANKING_DATA = json.load(_f)

_ACCOUNTS_CACHE: dict = {}          # banco -> {usuario: cuenta_dict}
_ACTIVE_SESSIONS: dict = {}         # atm_id -> usuario con sesion activa en ese banco


def auth(origin: str, destination: str, usuario: str, pin: str) -> dict:
    return build_message("AUTH", origin, destination, {"usuario": usuario, "pin": pin})


def withdraw(origin: str, destination: str, usuario: str, monto: float) -> dict:
    return build_message("WITHDRAW", origin, destination, {"usuario": usuario, "monto": monto})


def logout(origin: str, destination: str) -> dict:
    return build_message("LOGOUT", origin, destination, {})


def error(origin: str, destination: str, code: str, detalle: str) -> dict:
    return build_message("ERROR", origin, destination, {"code": code, "detalle": detalle})


def _accounts_for(banco: str) -> dict:
    if banco not in _ACCOUNTS_CACHE:
        cuentas = _BANKING_DATA.get(banco, {}).get("cuentas", [])
        _ACCOUNTS_CACHE[banco] = {c["usuario"]: c for c in cuentas}
    return _ACCOUNTS_CACHE[banco]


def handle_incoming(message: dict) -> dict:
    msg_type = message.get("type")
    atm_id = message.get("origin")
    banco = message.get("destination")
    payload = message.get("payload") or {}

    if msg_type == "AUTH":
        usuario = payload.get("usuario")
        pin = payload.get("pin")
        cuenta = _accounts_for(banco).get(usuario)

        if cuenta is not None and cuenta["pin"] == pin:
            _ACTIVE_SESSIONS[atm_id] = usuario
            print(f"[{banco}] LOGIN OK -> {atm_id} (usuario={usuario}, saldo={cuenta['saldo']})", flush=True)
            return build_message("AUTH", banco, atm_id, {"status": "ok", "saldo": cuenta["saldo"]})

        print(f"[{banco}] LOGIN DENEGADO -> {atm_id} (usuario={usuario})", flush=True)
        return build_message("AUTH", banco, atm_id, {"status": "denied", "message": "usuario o PIN invalido"})

    if msg_type == "WITHDRAW":
        usuario = _ACTIVE_SESSIONS.get(atm_id)
        if not usuario:
            print(f"[{banco}] RETIRO rechazado -> {atm_id}: sin sesion activa", flush=True)
            return error(banco, atm_id, "NOT_AUTHENTICATED", "inicia sesion antes de retirar")

        monto = payload.get("monto")
        cuenta = _accounts_for(banco)[usuario]

        if not isinstance(monto, (int, float)) or monto <= 0 or monto > cuenta["saldo"]:
            print(f"[{banco}] RETIRO RECHAZADO -> {atm_id} (usuario={usuario}, monto={monto})", flush=True)
            return build_message(
                "WITHDRAW", banco, atm_id,
                {"status": "error", "message": "monto invalido o saldo insuficiente", "saldo": cuenta["saldo"]},
            )

        cuenta["saldo"] -= monto
        print(f"[{banco}] RETIRO OK -> {atm_id} (usuario={usuario}, monto={monto}, saldo={cuenta['saldo']})", flush=True)
        return build_message("WITHDRAW", banco, atm_id, {"status": "ok", "saldo": cuenta["saldo"]})

    if msg_type == "LOGOUT":
        usuario = _ACTIVE_SESSIONS.pop(atm_id, None)
        print(f"[{banco}] LOGOUT -> {atm_id} (usuario={usuario})", flush=True)
        return build_message("LOGOUT", banco, atm_id, {"status": "ok"})

    return error(banco, atm_id, "UNKNOWN_TYPE", f"tipo no soportado: {msg_type}")
