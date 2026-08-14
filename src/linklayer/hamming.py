"""Codigo de Hamming generico: valido para cualquier (m, r) que cumpla
m + r + 1 <= 2^r. Los bits de paridad van en las posiciones potencia de 2
(1-indexado); el resto son bits de datos, en orden.

Para el Lab 3 se usa fijo en bloques de m=4 -> r=3 -> codeword de n=7 bits
(Hamming 7,4), ver `framing.py`.
"""
from __future__ import annotations


def _min_parity_bits(data_len: int) -> int:
    r = 0
    while data_len + r + 1 > (1 << r):
        r += 1
    return r


def _is_power_of_two(n: int) -> bool:
    return n > 0 and (n & (n - 1)) == 0


def encode(data_bits: str) -> str:
    """Inserta bits de paridad y devuelve el codeword completo."""
    if any(b not in "01" for b in data_bits):
        raise ValueError("encode espera una cadena de '0'/'1'")

    r = _min_parity_bits(len(data_bits))
    n = len(data_bits) + r

    codeword = ["0"] * n
    data_iter = iter(data_bits)
    for pos in range(1, n + 1):
        if not _is_power_of_two(pos):
            codeword[pos - 1] = next(data_iter)

    for bit in range(r):
        parity_pos = 1 << bit
        parity = 0
        for pos in range(1, n + 1):
            if pos & parity_pos and codeword[pos - 1] == "1":
                parity ^= 1
        codeword[parity_pos - 1] = str(parity)

    return "".join(codeword)


def decode(codeword: str) -> tuple[str, bool, int]:
    """Detecta y corrige hasta 1 bit erroneo. Devuelve (datos, hubo_error, posicion_error)."""
    if any(b not in "01" for b in codeword):
        raise ValueError("decode espera una cadena de '0'/'1'")

    n = len(codeword)
    r = 0
    while (1 << r) <= n:
        r += 1

    syndrome = 0
    for bit in range(r):
        parity_pos = 1 << bit
        parity = 0
        for pos in range(1, n + 1):
            if pos & parity_pos and codeword[pos - 1] == "1":
                parity ^= 1
        if parity:
            syndrome |= parity_pos

    corrected = list(codeword)
    error_pos = 0
    if syndrome and syndrome <= n:
        error_pos = syndrome
        corrected[error_pos - 1] = "1" if corrected[error_pos - 1] == "0" else "0"

    data_bits = "".join(bit for pos, bit in enumerate(corrected, start=1) if not _is_power_of_two(pos))
    return data_bits, bool(error_pos), error_pos
