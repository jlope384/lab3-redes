"""Empaquetado del plano de datos: texto <-> bits, y aplicacion de Hamming(7,4)
en bloques de 4 bits de datos (7 bits de codeword) a una cadena de bits
arbitraria, tal como pide la seccion 3.2 del enunciado.
"""
from __future__ import annotations

from src.linklayer.hamming import decode as hamming_decode_block
from src.linklayer.hamming import encode as hamming_encode_block

BLOCK_DATA_BITS = 4
BLOCK_CODEWORD_BITS = 7
PADDING_HEADER_BITS = 2  # alcanza para representar 0-3 bits de relleno


def text_to_bits(text: str) -> str:
    return "".join(f"{byte:08b}" for byte in text.encode("utf-8"))


def bits_to_text(bits: str) -> str:
    if len(bits) % 8 != 0:
        raise ValueError("la cantidad de bits debe ser multiplo de 8 para reconstruir texto")
    raw = bytes(int(bits[i:i + 8], 2) for i in range(0, len(bits), 8))
    return raw.decode("utf-8")


def encode_frame(bits: str) -> str:
    """Aplica Hamming(7,4) bloque a bloque sobre `bits`.

    Antepone un header de 2 bits con la cantidad de ceros de relleno (0-3)
    agregados al final para que `bits` sea multiplo de 4, necesario para
    poder reconstruir la longitud original al decodificar.
    """
    if any(b not in "01" for b in bits):
        raise ValueError("encode_frame espera una cadena de '0'/'1'")

    padding = (-len(bits)) % BLOCK_DATA_BITS
    padded = bits + "0" * padding
    blocks = (padded[i:i + BLOCK_DATA_BITS] for i in range(0, len(padded), BLOCK_DATA_BITS))
    codewords = "".join(hamming_encode_block(block) for block in blocks)
    return f"{padding:0{PADDING_HEADER_BITS}b}" + codewords


def decode_frame(frame: str) -> str:
    """Revierte `encode_frame`: corrige hasta 1 bit por bloque y quita el relleno."""
    if len(frame) < PADDING_HEADER_BITS:
        raise ValueError("frame demasiado corto para contener el header de padding")

    padding = int(frame[:PADDING_HEADER_BITS], 2)
    payload = frame[PADDING_HEADER_BITS:]
    if len(payload) % BLOCK_CODEWORD_BITS != 0:
        raise ValueError("longitud de payload codificado invalida")

    blocks = (payload[i:i + BLOCK_CODEWORD_BITS] for i in range(0, len(payload), BLOCK_CODEWORD_BITS))
    data_bits = "".join(hamming_decode_block(block)[0] for block in blocks)
    return data_bits[:-padding] if padding else data_bits
