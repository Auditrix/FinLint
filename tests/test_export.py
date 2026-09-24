"""Tests for export.py, the JSON door out of the dependency map."""

import json

from finlint.graph.export import export_graph, graph_to_dict
from finlint.graph.graph import Graph

# The five cell example from the notebook:
#   A1 = 10        A2 = A1*2        A3 = A1+A2        A4 = A3*2        A5 = 25
# A5 reads nothing and nothing reads it, so it never appears in the graph.
EXPECTED_NODES = ["S!A1", "S!A2", "S!A3", "S!A4"]
EXPECTED_EDGES = [
    ["S!A1", "S!A2"],
    ["S!A1", "S!A3"],
    ["S!A2", "S!A3"],
    ["S!A3", "S!A4"],
]


def build_sample():
    """Build the five cell graph by hand, so every answer is known in advance."""
    return Graph(
        feeds={
            "S!A2": {"S!A1"},
            "S!A3": {"S!A1", "S!A2"},
            "S!A4": {"S!A3"},
        },
        feeds_into={
            "S!A1": {"S!A2", "S!A3"},
            "S!A2": {"S!A3"},
            "S!A3": {"S!A4"},
        },
    )


def test_nodes_sorted():
    """Every cell appears once, in a fixed order."""
    assert graph_to_dict(build_sample())["nodes"] == EXPECTED_NODES


def test_edges_are_pairs():
    """Each link is its own [from, to] pair, never a set."""
    assert graph_to_dict(build_sample())["edges"] == EXPECTED_EDGES


def test_no_sets_survive():
    """A set would crash json.dump, so nothing in the output may be one."""
    data = graph_to_dict(build_sample())
    for edge in data["edges"]:
        assert isinstance(edge, list)
        assert all(isinstance(cell, str) for cell in edge)


def test_same_every_run():
    """The same graph must always give exactly the same output."""
    graph = build_sample()
    assert graph_to_dict(graph) == graph_to_dict(graph)


def test_writes_readable_json(tmp_path):
    """The written file is valid JSON and holds what we put in it."""
    path = tmp_path / "graph.json"
    export_graph(build_sample(), path)

    with open(path, encoding="utf-8") as f:
        written = json.load(f)

    assert written == graph_to_dict(build_sample())
    assert written["nodes"] == EXPECTED_NODES
    assert written["edges"] == EXPECTED_EDGES


def test_empty_graph_exports_cleanly(tmp_path):
    """A workbook with no formulas still produces a valid, empty map."""
    path = tmp_path / "empty.json"
    export_graph(Graph(), path)

    with open(path, encoding="utf-8") as f:
        written = json.load(f)

    assert written == {"nodes": [], "edges": []}
