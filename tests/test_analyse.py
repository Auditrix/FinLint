from finlint.graph.analyse import blast_radius, dependents, find_cycles, precedents
from finlint.graph.graph import Graph


def make_five_cell_graph():
    return Graph(
        feeds={
            "S!A1": set(),
            "S!A2": {"S!A1"},
            "S!A3": {"S!A1", "S!A2"},
            "S!A4": {"S!A3"},
            "S!A5": set(),
        },
        feeds_into={
            "S!A1": {"S!A2", "S!A3"},
            "S!A2": {"S!A3"},
            "S!A3": {"S!A4"},
        },
    )


def test_precedents_and_dependents():
    graph = make_five_cell_graph()

    assert precedents(graph, "S!A3") == {"S!A1", "S!A2"}
    assert dependents(graph, "S!A1") == {"S!A2", "S!A3"}


def test_missing_cells_return_an_empty_set():
    graph = make_five_cell_graph()

    assert precedents(graph, "S!A6") == set()
    assert dependents(graph, "S!A5") == set()


def test_blast_radius_uses_every_downstream_cell():
    graph = make_five_cell_graph()

    assert blast_radius(graph, "S!A1") == {"S!A2", "S!A3", "S!A4"}
    assert blast_radius(graph, "S!A5") == set()


def test_blast_radius_does_not_include_the_starting_cell():
    graph = Graph(
        feeds_into={
            "S!A1": {"S!A2"},
            "S!A2": {"S!A1"},
        }
    )

    assert blast_radius(graph, "S!A1") == {"S!A2"}


def test_find_cycles_finds_loops_and_self_loops():
    graph = Graph(
        feeds_into={
            "S!A1": {"S!A2"},
            "S!A2": {"S!A3"},
            "S!A3": {"S!A1", "S!A4"},
            "S!A4": set(),
            "S!A5": {"S!A5"},
        }
    )

    assert find_cycles(graph) == {"S!A1", "S!A2", "S!A3", "S!A5"}


def test_find_cycles_handles_a_large_graph():
    node_count = 14_001
    edges = {}

    for number in range(1, node_count):
        edges[f"S!A{number}"] = {f"S!A{number + 1}"}

    edges[f"S!A{node_count}"] = set()
    graph = Graph(feeds_into=edges)

    assert find_cycles(graph) == set()
