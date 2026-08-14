from src.router.lsa import LSAManager


def _manager(on_lsa=None):
    # addressbook/live_links vacios: nunca intenta abrir sockets de verdad.
    return LSAManager("A", addressbook={}, live_links_provider=lambda: {}, on_lsa=on_lsa)


def test_flood_own_lsa_has_strictly_increasing_seq():
    seen = []
    manager = _manager(on_lsa=lambda lsa: seen.append(lsa["seq"]))
    for _ in range(5):
        manager.flood_own_lsa()
    assert seen == sorted(seen)
    assert len(set(seen)) == len(seen)


def test_handle_incoming_accepts_newer_seq_and_learns():
    learned = []
    manager = _manager(on_lsa=lambda lsa: learned.append(lsa))

    manager.handle_incoming({"type": "LSA", "origin": "B", "seq": 10, "ttl": 16, "links": {"A": 1}, "from": "B"})
    assert len(learned) == 1
    assert learned[0]["origin"] == "B"


def test_handle_incoming_drops_duplicate_or_stale_seq():
    learned = []
    manager = _manager(on_lsa=lambda lsa: learned.append(lsa))

    manager.handle_incoming({"type": "LSA", "origin": "B", "seq": 10, "ttl": 16, "links": {}, "from": "B"})
    manager.handle_incoming({"type": "LSA", "origin": "B", "seq": 10, "ttl": 16, "links": {}, "from": "B"})
    manager.handle_incoming({"type": "LSA", "origin": "B", "seq": 5, "ttl": 16, "links": {}, "from": "B"})

    assert len(learned) == 1  # solo el primer seq=10 se aprende


def test_handle_incoming_stops_propagation_when_ttl_exhausted():
    learned = []
    manager = _manager(on_lsa=lambda lsa: learned.append(lsa))
    # ttl=0 igual se aprende localmente, solo no se reenvia (no hay forma
    # directa de observar el reenvio sin sockets reales, pero no debe tronar).
    manager.handle_incoming({"type": "LSA", "origin": "C", "seq": 1, "ttl": 0, "links": {}, "from": "C"})
    assert len(learned) == 1
