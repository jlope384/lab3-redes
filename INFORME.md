# Informe — Lab 3: Protocolos de Enrutamiento

**Curso:** Redes — UVG
**Fecha:** 2026-08-13
**Implementación:** nodo router "A" (una de 3 parejas / 6 nodos de la topología)

## 1. Introducción

Este laboratorio implementa un protocolo de enrutamiento tipo *link-state* (similar a OSPF
simplificado) sobre una red superpuesta (overlay) de 6 nodos, construida entre 3 parejas usando
Tailscale como red de transporte física. Cada pareja implementa de forma independiente su propio
router, pero las 3 parejas acordaron por adelantado un formato de mensajes común (Anexo A) para
que las 6 implementaciones puedan interoperar sin conocer el código interno de las demás.

Sobre esa capa de enrutamiento corre además una aplicación de prueba tipo cajero automático (ATM)
— servidor bancario, que ejercita el envío de datos extremo a extremo a través de la red de routers,
incluyendo corrección de errores a nivel de enlace con código de Hamming(7,4).

## 2. Objetivos

- Implementar descubrimiento de vecinos vivos (HELLO) y detección de caída de enlaces.
- Implementar difusión de estado de enlaces (LSA) por flooding controlado (anti-loop por número
  de secuencia y TTL).
- Calcular la ruta más corta hacia cualquier nodo de la red con Dijkstra, a partir del grafo
  reconstruido de los LSA recibidos.
- Reenviar (forward) paquetes de datos salto a salto según la tabla de enrutamiento calculada.
- Codificar/decodificar los datos con Hamming(7,4) para detectar y corregir errores de un bit
  por bloque.
- Interoperar con las implementaciones de las otras 2 parejas sobre la misma topología de 6 nodos.

## 3. Formato del protocolo acordado entre las 3 parejas

Formato definido y firmado en conjunto antes de implementar (`Propuesta_protocolo_Lab3-1.pdf`),
para garantizar interoperabilidad entre las 3 implementaciones independientes.

### 3.1 Paquete HELLO — descubrimiento de vecinos directos

```json
{"type": "HELLO", "from": "<ip_origen>"}
```

Cada nodo envía HELLO periódico a sus vecinos directos; si un vecino no responde en un tiempo X,
el enlace se considera caído.

### 3.2 Paquete LSA — difusión del estado de enlaces (flooding)

```json
{
  "type": "LSA",
  "origin": "<ip_creador>",
  "seq": 0,
  "ttl": 16,
  "links": {"<ip_vecino>": 1},
  "from": "<ip_emisor_actual>"
}
```

Al recibir un LSA, el nodo lo reenvía a todos sus vecinos **excepto** por donde le llegó.

### 3.3 Manejo de ciclos en el flooding

- Cada nodo guarda el último `seq` recibido por cada `origin`.
- Si llega un LSA con `seq` menor o igual al guardado, se descarta y no se reenvía.
- `ttl` decrementa 1 en cada salto; al llegar a 0 el paquete se descarta.

### 3.4 Mensajes de datos ATM–Banco

```json
{
  "type": "AUTH | WITHDRAW | ERROR | LOGOUT",
  "origin": "<ip_nodo_ATM>",
  "destination": "<ip_nodo_servidor>",
  "payload": {}
}
```

| Tipo       | Campos de `payload`                 |
|------------|--------------------------------------|
| `AUTH`     | `{"user": ..., "pin": ...}`          |
| `WITHDRAW` | `{"cuenta": ..., "monto": ...}`      |
| `ERROR`    | `{"code": ..., "detalle": ...}`      |
| `LOGOUT`   | `{}`                                  |

`origin`/`destination` son la IP del nodo cliente (ATM) y del servidor (banco), **no** de los
routers intermedios.

## 4. Arquitectura de la implementación

El nodo (`src/node.py`) levanta 4 componentes concurrentes (hilos) sobre TCP:

```
             ┌────────────────────────────────────────┐
             │                 node.py                 │
             │                                          │
  HELLO ─────┼──▶ HelloManager  ──on_link_change──▶ LSAManager ─┐
             │        │                                        │
             │        ▼                                        ▼
             │  live_neighbors()                       NetworkGraph
             │                                                │
             │                                                ▼
             │                                       compute_routes (Dijkstra)
             │                                                │
             │                                                ▼
             │                              data/nodo_<id>_tabla_enrutamiento.csv
             │                                                │
  datos ─────┼──▶ ForwardingLayer ◀────────────────────────────┘
             └────────────────────────────────────────┘
```

### 4.1 Transporte (`src/transport/sockets.py`)

TCP puro. Cada envío abre una conexión corta, manda **una línea terminada en `\n`** y cierra
(no hay conexión persistente entre vecinos, ni prefijo de longitud). Cada nodo expone dos
puertos: uno de **datos** (`config/nodos.json`) y uno de **control** = `puerto_datos + 1000`,
donde llegan HELLO y LSA.

### 4.2 Descubrimiento de vecinos (`src/router/hello.py`)

`HelloManager` manda un HELLO cada 2s a cada vecino configurado (sin esperar ACK) y corre un
watchdog que marca un enlace como `DOWN` si no se ve HELLO de ese vecino en 6s. Los vecinos
"configurados" (`topologia.json`) son la fuente de verdad estática; los "vivos" son el
subconjunto de esos que respondieron HELLO recientemente — es lo que se anuncia en el LSA propio.

### 4.3 Difusión de estado de enlaces (`src/router/lsa.py`)

`LSAManager` arma y reenvía LSAs. Dos detalles de diseño:

- **`seq` como timestamp en ms** (estrictamente creciente) en vez de un contador en memoria desde
  0: así, si el proceso se reinicia, el siguiente LSA sigue teniendo un `seq` mayor al último que
  los demás nodos ya conocían de este origen, y no se descarta como "viejo".
- **Re-flood periódico** cada 15s (`LSA_REFRESH_INTERVAL` en `node.py`) además de al detectar un
  cambio de enlace, para cubrir el caso de un vecino que aún no escuchaba en el primer flood, o
  que se reinició sin que su vecino detectara la caída por timeout de HELLO.

### 4.4 Cálculo de rutas (`src/router/routing.py`, `network_graph.py`)

`NetworkGraph` guarda la última vista de adyacencias por `origin` (se reemplaza completa en cada
LSA nuevo, no se mezcla — un LSA siempre refleja el estado *actual* de los enlaces del emisor).
`compute_routes` corre Dijkstra clásico con heap sobre ese grafo y devuelve, por destino,
`(costo, siguiente_salto)`. El resultado se escribe a
`data/nodo_<id>_tabla_enrutamiento.csv`.

### 4.5 Plano de datos y reenvío (`src/dataplane/forwarding.py`)

`ForwardingLayer` recibe un frame, lo decodifica (Hamming, ver 4.6) y decide:

- Si el `destination` es un endpoint (ATM/banco, no un router) cuyo gateway soy yo →
  entrega directa por IP/puerto real del endpoint.
- Si el gateway de ese endpoint es otro router → se reenvía hacia ese router siguiendo la
  tabla de ruteo.
- Si `destination` ya es un id de router → se reenvía directo según la tabla.

### 4.6 Capa de enlace — Hamming(7,4) (`src/linklayer/hamming.py`, `framing.py`)

Implementación genérica de Hamming (funciona para cualquier `(m, r)` válido), usada fija en
bloques de **4 bits de datos → 7 bits de codeword**. `framing.py` convierte el JSON del mensaje a
bits UTF-8, lo parte en bloques de 4, aplica Hamming a cada bloque, y antepone un header de 2 bits
con el padding usado (0-3 ceros) para poder reconstruir la longitud exacta al decodificar. Corrige
hasta 1 bit erróneo por bloque de 7.

### 4.7 Aplicación de prueba ATM–Banco (`src/endpoints/`, `src/dataplane/banking.py`)

`atm.py` es un cliente de consola (login, retiro, logout) que arma mensajes `AUTH`/`WITHDRAW`/
`LOGOUT` y los manda a su router gateway; `bank.py` es un servidor que valida usuario/PIN contra
`data/banking_data.json`, mantiene sesiones activas en memoria y responde con el mismo `type`.

## 5. Configuración y despliegue

- `config/nodos.json`: IP y puerto de datos de cada nodo/endpoint.
- `config/topologia.json`: vecinos directos y costo de enlace por nodo.
- `config/endpoints.json`: mapea cada ATM/servidor a su router gateway.
- **Red de transporte:** Tailscale. Los 6 nodos (3 parejas) se unen a la misma tailnet; cada quien
  obtiene su IP real con `tailscale ip -4` y esa IP reemplaza el id de prueba local (`A`, `B`, ...)
  en `config/*.json` antes de la prueba de interoperabilidad, ya que el protocolo (sección 3)
  exige que `origin`/`destination`/`from` sean la IP real del nodo.

## 6. Pruebas

### 6.1 Pruebas unitarias (`pytest`, 10 pruebas, todas pasan)

| Archivo | Cubre |
|---|---|
| `tests/test_hamming.py` | Roundtrip de Hamming(7,4) sin error; corrección de 1 bit erróneo en cualquier posición del codeword; roundtrip de framing completo (texto → bits → frame → bits → texto) con texto vacío, ASCII y UTF-8 con acentos/símbolos. |
| `tests/test_lsa_flooding.py` | `seq` estrictamente creciente al re-floodear; un LSA nuevo se aprende; un LSA duplicado o con `seq` viejo se descarta; un LSA con `ttl=0` se aprende localmente pero no se reenvía. |
| `tests/test_routing.py` | Dijkstra prefiere una ruta multi-salto más barata sobre un enlace directo más caro; un nodo inalcanzable no aparece en las rutas; el nodo origen nunca aparece en su propia tabla. |

### 6.2 Prueba local (single-machine)

Levantar varios nodos en `127.0.0.1` con puertos distintos (`config/nodos.json` de prueba) y
verificar que la tabla de enrutamiento de cada uno converge al costo/óptimo esperado según
`topologia.json`, y que un mensaje ATM→Banco llega y responde correctamente atravesando 1+ saltos.

### 6.3 Prueba de interoperabilidad (con las otras 2 parejas) — **pendiente**

Requiere los 6 nodos conectados a la misma tailnet, IPs reales cargadas en `config/nodos.json`, y
la topología real de 6 nodos asignada al grupo. Estado al momento de este informe: la tailnet
compartida ya está armada (4 de 6 integrantes conectados), aún no se ha corrido la prueba conjunta
de los 6 routers.

## 7. Observaciones y desviaciones detectadas frente al protocolo acordado

Al revisar la implementación contra el PDF de protocolo (sección 3), se detectaron 2 diferencias
en los nombres de campo de `payload` que **deben corregirse antes de la prueba de
interoperabilidad**, porque un banco de otra pareja podría no reconocer los campos:

- `AUTH`: el protocolo pide `"user"`; la implementación actual (`src/dataplane/banking.py`) usa
  `"usuario"`.
- `WITHDRAW`: el protocolo pide `"cuenta"`; la implementación actual usa `"usuario"` (además,
  actualmente identifica la cuenta a retirar por el usuario de la sesión activa, no por un
  número de cuenta explícito en el mensaje).

*(Si quieres, puedo corregir esto en el código antes de la prueba conjunta — es un cambio pequeño
en `banking.py`, `atm.py` y `bank.py`.)*

## 8. Conclusiones

- La implementación cubre correctamente el ciclo completo link-state: descubrimiento de vecinos,
  difusión de estado por flooding con protección anti-loop (seq + TTL), cálculo de rutas óptimas
  y reenvío de datos con corrección de errores a nivel de enlace.
- El diseño de `seq` basado en timestamp (en vez de contador en memoria) resuelve de forma simple
  el problema de reinicios de proceso sin coordinación explícita entre nodos.
- Las 10 pruebas unitarias cubren los 3 componentes de mayor riesgo de bugs sutiles: aritmética de
  Hamming, lógica anti-loop de flooding, y Dijkstra.
- Quedan 2 pendientes bloqueantes antes de dar la implementación por completa: (1) corregir los
  nombres de campo de `payload` bancario para cumplir el protocolo acordado, y (2) ejecutar y
  documentar la prueba de interoperabilidad real con las otras 2 parejas sobre Tailscale.

## Anexo A — Protocolo acordado (fuente)

`Propuesta_protocolo_Lab3-1.pdf`, acordado entre las 3 parejas antes de implementar.
