from __future__ import annotations

import heapq


def topological_order(
    sort_keys: dict[str, tuple],
    edges: list[tuple[str, str]],
) -> tuple[list[str], list[str]]:
    """Kahn's algorithm with stable tie-breaking.

    sort_keys: node_id -> (sort_order, node_id). Lower is picked first.
    edges: (source, target) pairs; every endpoint must be in sort_keys.
    Returns (order, leftover). leftover is non-empty only if there is a cycle.
    """
    indegree = {n: 0 for n in sort_keys}
    children: dict[str, list[str]] = {n: [] for n in sort_keys}
    for src, dst in edges:
        children[src].append(dst)
        indegree[dst] += 1

    ready = [(sort_keys[n], n) for n, d in indegree.items() if d == 0]
    heapq.heapify(ready)

    order: list[str] = []
    while ready:
        _, node = heapq.heappop(ready)
        order.append(node)
        for child in children[node]:
            indegree[child] -= 1
            if indegree[child] == 0:
                heapq.heappush(ready, (sort_keys[child], child))

    placed = set(order)
    leftover = sorted(n for n in sort_keys if n not in placed)
    return order, leftover