from src.router.routing import compute_routes


def test_prefers_cheaper_multi_hop_over_direct_link():
    graph = {
        "A": {"B": 1, "C": 4},
        "B": {"A": 1, "C": 2},
        "C": {"A": 4, "B": 2},
    }
    routes = compute_routes(graph, "A")
    assert routes["B"] == (1, "B")
    assert routes["C"] == (3, "B")  # A->B->C (1+2) es mas barato que A->C directo (4)


def test_unreachable_node_is_not_in_routes():
    graph = {"A": {"B": 1}, "B": {"A": 1}, "C": {}}
    routes = compute_routes(graph, "A")
    assert "C" not in routes


def test_source_never_in_own_routes():
    graph = {"A": {"B": 1}, "B": {"A": 1}}
    routes = compute_routes(graph, "A")
    assert "A" not in routes
