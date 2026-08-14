# Lab 3 — Protocolos de Enrutamiento (mi implementación)

Implementación propia de Link State (HELLO, LSA con flooding por seq/ttl, Dijkstra) más
capa de datos con Hamming(7,4), siguiendo el protocolo acordado con las otras 2 parejas
para poder interoperar sobre la red de 6 nodos (Tailscale).

## Formato del protocolo (acordado con las otras parejas)

- Transporte: TCP. Un mensaje por línea (`\n`), sin prefijo de longitud. Cada envío abre
  una conexión corta, manda la línea y cierra.
- Puertos: un único puerto por nodo (`config/nodos.json`) para control y datos. Quien recibe
  distingue mirando el primer carácter de la línea: `{` = control (HELLO/LSA, JSON), `0`/`1` =
  datos (frame ya codificado con Hamming(7,4)).
- `HELLO`: `{"type": "HELLO", "from": "<id>"}`, cada 2s, sin ACK; 6s sin verlo = enlace DOWN.
- `LSA`: `{"type": "LSA", "origin": <id>, "seq": <int>, "ttl": <int>, "links": {...}, "from": <id>}`.
  `origin` no cambia al reenviar; `from` sí (queda como el último salto). `seq` se deriva de
  un timestamp en ms para que sobreviva a reinicios del proceso sin que los demás nodos lo
  descarten como "viejo".
- Datos: `{"type": ..., "origin": <id>, "destination": <id>, "payload": {...}}`, con Hamming(7,4)
  aplicado en bloques de 4 bits sobre el JSON serializado a UTF-8.
- `origin`/`destination`/`from` deben ser la IP real (Tailscale) de cada nodo antes de la
  prueba de interoperabilidad — los ids `A`, `B`, ... de `config/*.json` son solo para pruebas
  locales.

## Requisitos

- Python 3.10+
- `pip install -r requirements.txt` (solo para correr los tests)

## Configuración

- `config/nodos.json`: IP y puerto (plano de datos) de cada nodo.
- `config/topologia.json`: vecinos directos y costo de enlace de cada nodo (placeholder —
  reemplazar por la topología real asignada dentro del grupo de 6 nodos).
- `config/endpoints.json`: mapea cada ATM/servidor (no son routers) a su router gateway.

## Correr nodos router localmente

```bash
python -m src.node A
python -m src.node B
# ...un proceso por nodo, cada uno en su propia terminal
```

Cada nodo imprime su tabla (`data/nodo_<id>_tabla_enrutamiento.csv`) al recalcularla.

## Cliente/servidor de prueba (ATM–Banco)

```bash
python -m src.endpoints.bank BANCO1 <gateway_id>
python -m src.endpoints.atm ATM1 <gateway_id> BANCO1
```

## Tests

```bash
pytest
```

## Antes de la prueba con las otras 2 parejas

1. Todos en la misma tailnet de Tailscale (`tailscale ip -4` para obtener la IP de cada quien).
2. Reemplazar las claves de `config/nodos.json` (y las de `topologia.json`/`endpoints.json`)
   por las IPs Tailscale reales, según la topología de 6 nodos asignada.
3. Confirmar con las otras parejas que el esquema de puerto único y el formato de HELLO/LSA
   de arriba son los mismos que usan ellas.
