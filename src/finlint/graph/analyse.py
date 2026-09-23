"""Answer questions using the dependency graph."""

from finlint.graph.graph import Graph


def precedents(graph: Graph, cell: str) -> set[str]:
    """Return the cells that this cell reads directly."""
    return graph.feeds.get(cell, set())


def dependents(graph: Graph, cell: str) -> set[str]:
    """Return the cells that read this cell directly."""
    return graph.feeds_into.get(cell, set())


def blast_radius(graph: Graph, cell: str) -> set[str]:
    """Return every cell affected after this cell changes."""
    to_visit = list(dependents(graph, cell))
    seen = set()

    while to_visit:
        current = to_visit.pop()

        if current == cell or current in seen:
            continue

        seen.add(current)

        for next_cell in dependents(graph, current):
            if next_cell not in seen:
                to_visit.append(next_cell)

    return seen


def _get_finish_order(edges, nodes):
    """Visit every node and remember when each path finishes."""
    seen = set()
    finish_order = []

    for start in nodes:
        if start in seen:
            continue

        to_visit = [(start, False)]

        while to_visit:
            current, finished = to_visit.pop()

            if finished:
                finish_order.append(current)
                continue

            if current in seen:
                continue

            seen.add(current)
            to_visit.append((current, True))

            for next_cell in edges.get(current, set()):
                if next_cell not in seen:
                    to_visit.append((next_cell, False))

    return finish_order


def find_cycles(graph: Graph) -> set[str]:
    """Return every cell that is part of a dependency loop."""
    edges = graph.feeds_into
    nodes = set(edges)

    for next_cells in edges.values():
        nodes.update(next_cells)

    finish_order = _get_finish_order(edges, nodes)

    # Reversing every arrow lets us collect cells that belong to the same loop.
    reverse_edges = {node: set() for node in nodes}
    for cell, next_cells in edges.items():
        for next_cell in next_cells:
            reverse_edges[next_cell].add(cell)

    checked = set()
    cycle_cells = set()

    for start in reversed(finish_order):
        if start in checked:
            continue

        group = set()
        to_visit = [start]

        while to_visit:
            current = to_visit.pop()
            if current in checked:
                continue

            group.add(current)
            checked.add(current)
            to_visit.extend(reverse_edges.get(current, set()))

        if len(group) > 1:
            cycle_cells.update(group)
        elif start in edges.get(start, set()):
            cycle_cells.add(start)

    return cycle_cells
