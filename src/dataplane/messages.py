"""Serializacion de mensajes del plano de datos, formato acordado:

{ "type": ..., "origin": <id_cliente_o_servidor>, "destination": <id_cliente_o_servidor>, "payload": {...} }
"""
from __future__ import annotations

import json


def build_message(msg_type: str, origin: str, destination: str, payload: dict) -> dict:
    return {
        "type": msg_type,
        "origin": origin,
        "destination": destination,
        "payload": payload,
    }


def to_json(message: dict) -> str:
    return json.dumps(message)


def from_json(raw: str) -> dict:
    return json.loads(raw)
