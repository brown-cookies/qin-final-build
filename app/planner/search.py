"""Dijkstra over the shared graph with per-query virtual start/end (never stored in the graph)."""
import heapq

START = ("start",)
END = ("end",)


def find_path(graph, start_stops, end_stops):
    """Lowest-cost node list from START to END, or None.

    start_stops / end_stops: [(stop_id, walk_metres)]. Walk cost is km x walk_cost_factor.
    """
    factor = graph.walk_cost_factor
    end_cost = {sid: m / 1000.0 * factor for sid, m in end_stops}
    best = {START: 0.0}
    prev = {}
    heap = [(0.0, 0, START)]
    tie = 1
    done = set()
    while heap:
        cost, _, node = heapq.heappop(heap)
        if node in done:
            continue
        done.add(node)
        if node == END:
            path = [END]
            while path[-1] != START:
                path.append(prev[path[-1]])
            path.reverse()
            return path
        if node == START:
            edges = [(("at", sid), m / 1000.0 * factor) for sid, m in start_stops]
        else:
            # A stop reached by walking is ("wk", id): it may only board or finish, so
            # walk edges cannot chain past TRANSFER_RADIUS_M.
            src = ("at", node[1]) if node[0] == "wk" else node
            edges = []
            for n, c, kind in graph.adj[src]:
                if kind == "walk":
                    if node[0] == "wk":
                        continue
                    n = ("wk", n[1])
                edges.append((n, c))
            if node[0] in ("at", "wk") and node[1] in end_cost:
                edges.append((END, end_cost[node[1]]))
        for nxt, c in edges:
            nc = cost + c
            if nc < best.get(nxt, float("inf")):
                best[nxt] = nc
                prev[nxt] = node
                heapq.heappush(heap, (nc, tie, nxt))
                tie += 1
    return None
