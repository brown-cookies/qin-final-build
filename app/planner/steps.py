"""Turns a node path into SPEC 6.3 steps and the one-line summary."""
from app.planner.graph import haversine_m

START_LABEL = "Your start point"
END_LABEL = "Your destination"


def color_label(color):
    return "Dark yellow" if color == "darkyellow" else color.capitalize()


def build_steps(graph, path, start, end):
    """path: node list from find_path; start/end: (lat, lng). Returns the steps list."""
    nodes = path[1:-1]
    name = lambda sid: graph.stops[sid].name  # noqa: E731
    first = graph.stops[nodes[0][1]]
    pending = haversine_m(start[0], start[1], first.lat, first.lng)
    steps = []
    ride = None
    alighted = None  # stop_id of the last alight
    walk_acc = 0.0
    cur = nodes[0][1]
    for a, b in zip(nodes, nodes[1:]):
        if a[0] in ("at", "wk") and b[0] == "on":
            route = graph.routes[b[1]]
            if alighted is None:
                steps.append({"type": "walk", "from": START_LABEL, "to": name(a[1]), "distance_m": round(pending)})
            else:
                steps.append({
                    "type": "transfer", "from": name(alighted), "to": name(a[1]),
                    "walk_m": round(walk_acc), "to_color": route["color"],
                })
            ride = {"route": route, "from": a[1], "passed": 0, "dist": 0.0}
        elif a[0] == "on" and b[0] == "on":
            ids = ride["route"]["stops"]
            ride["dist"] += graph.dist_m(ids[a[2]], ids[b[2]])
            ride["passed"] += 1
        elif a[0] == "on" and b[0] == "at":
            steps.append({
                "type": "ride", "color": ride["route"]["color"], "direction": ride["route"]["direction"],
                "from": name(ride["from"]), "to": name(b[1]),
                "stops_passed": ride["passed"], "distance_m": round(ride["dist"]),
            })
            alighted, walk_acc, ride, cur = b[1], 0.0, None, b[1]
        else:  # at -> at walk
            d = graph.dist_m(a[1], b[1])
            if alighted is None:
                pending += d
            else:
                walk_acc += d
            cur = b[1]
    last = graph.stops[cur]
    final = haversine_m(last.lat, last.lng, end[0], end[1])
    if alighted is None:
        steps.append({"type": "walk", "from": START_LABEL, "to": name(cur), "distance_m": round(pending)})
        origin = name(cur)
    else:
        final += walk_acc
        origin = name(alighted)
    steps.append({"type": "walk", "from": origin, "to": END_LABEL, "distance_m": round(final)})
    return steps


def build_summary(steps):
    parts = [f"Walk to {steps[0]['to']}"]
    for i, s in enumerate(steps[1:-1], start=1):
        if s["type"] == "ride":
            if steps[i - 1]["type"] == "transfer":
                parts.append(f"get off at {s['to']}")  # the transfer part already named the color
            else:
                parts.append(f"ride {color_label(s['color'])} to {s['to']}")
        elif s["type"] == "transfer":
            parts.append(f"transfer to {color_label(s['to_color'])}")
    parts.append("walk to your destination")
    return ", ".join(parts) + "."
