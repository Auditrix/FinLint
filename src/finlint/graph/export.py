"""Write the dependency map out as JSON, so an interface can draw it later.

Nothing is calculated here. The graph is only reshaped into plain nodes and
edges, because JSON cannot hold a Python set.
"""

import json

from finlint.graph.graph import Graph


def graph_to_dict(graph: Graph):
    """Convert the graph to a plain dictionary of nodes and edges, ready for JSON.

    Everything is sorted, so the same graph always gives exactly the same
    output. That is what makes the result testable.
    """
    data = {}

    # Every cell that appears at either end of a link.
    data["nodes"] = sorted(graph.feeds.keys() | graph.feeds_into.keys())

    # One pair per link, written [from, to], the way the number flows.
    data["edges"] = sorted(
        [source, target]
        for source, targets in graph.feeds_into.items()
        for target in targets
    )

    return data


def export_graph(graph: Graph, path: str, indent: int | None = None):
    """Export the graph to a JSON file at the given path.

    Leave indent as None for the real file. Pass indent=2 only while
    debugging, because spacing roughly triples the size on a large model.
    """
    result = graph_to_dict(graph)

    with open(path, "w", encoding="utf-8") as f:
        json.dump(result, f, indent=indent)
