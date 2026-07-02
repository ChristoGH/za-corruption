"""Render the evidence graph as a galaxy: a luminous core of the most-connected
entities, a fading halo of the rest, colour by detected cluster, over a nebula and
a deep starfield. Built to work as a profile image (square) and a banner (wide).

Pulls the most-connected people, organisations and places from Neo4j and lays them
out by who the testimony ties together. The single most-connected node sinks to the
bright galactic core; degree pulls others inward, so hubs cluster and the long tail
forms the outer arms. Colour is cluster (community), not type, for a vivid field.

Run (Neo4j up + claims loaded):
    uv run python scripts/graph_galaxy.py
    uv run python scripts/graph_galaxy.py --top 1100 --seed 7

Outputs: linkedin/graph_galaxy_square.png and linkedin/graph_galaxy_wide.png
"""

from __future__ import annotations

import argparse
import math
import os
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import Rectangle
import networkx as nx
import numpy as np

OUT = Path(__file__).resolve().parents[1] / "linkedin"

import commission_ingestion  # noqa: F401  (triggers .env load)
from neo4j import GraphDatabase

BG = "#04040b"
# Vivid cosmic palette, cycled by cluster.
PALETTE = [
    (1.00, 0.82, 0.30), (0.33, 0.85, 1.00), (1.00, 0.42, 0.80), (0.64, 0.45, 1.00),
    (0.40, 1.00, 0.70), (1.00, 0.55, 0.38), (0.45, 0.62, 1.00), (1.00, 0.92, 0.45),
    (0.55, 1.00, 0.95), (1.00, 0.35, 0.45),
]
# Nebula clouds (colour, relative position, relative size).
NEBULA = [
    ((0.20, 0.10, 0.45), (-0.25, 0.20), 1.15),
    ((0.05, 0.22, 0.40), (0.30, -0.10), 1.30),
    ((0.35, 0.08, 0.32), (0.10, 0.35), 0.95),
    ((0.10, 0.15, 0.38), (-0.10, -0.30), 1.10),
]
DEFAULT_HUBS = ["Matlala", "Senona", "Sibiya", "Mogotsi", "Mchunu", "Mkhwanazi",
                "SAPS", "Medicare", "Khumalo", "Masemola"]

Q_NODES = """
MATCH (e)
WHERE (e:Person OR e:Organisation OR e:Place) AND e.name IS NOT NULL
OPTIONAL MATCH (e)<-[:MENTIONS]-(cl:Claim)
WITH e, labels(e)[0] AS type, count(cl) AS deg
WHERE deg > 0
RETURN e.name AS name, type, deg ORDER BY deg DESC LIMIT $top
"""
Q_EDGES = """
MATCH (a)<-[:MENTIONS]-(cl:Claim)-[:MENTIONS]->(b)
WHERE a.name IN $names AND b.name IN $names AND a.name < b.name
RETURN a.name AS src, b.name AS dst, count(cl) AS w
"""


def fetch(top: int):
    uri = os.environ.get("NEO4J_URI", "bolt://localhost:7687")
    user = os.environ.get("NEO4J_USER", "neo4j")
    pwd = os.environ.get("NEO4J_PASSWORD", "changeme")
    driver = GraphDatabase.driver(uri, auth=(user, pwd))
    try:
        with driver.session() as s:
            nodes = [dict(r) for r in s.run(Q_NODES, top=top)]
            names = [n["name"] for n in nodes]
            edges = [dict(r) for r in s.run(Q_EDGES, names=names)]
    finally:
        driver.close()
    return nodes, edges


def layout(nodes, edges, seed: int):
    G = nx.Graph()
    for n in nodes:
        G.add_node(n["name"], **n)
    for e in edges:
        if e["w"] > 0:
            G.add_edge(e["src"], e["dst"], weight=math.log1p(e["w"]))

    pos = nx.spring_layout(G, k=0.22, iterations=160, weight="weight", seed=seed)
    p = np.array([pos[n["name"]] for n in nodes], dtype=float)
    centre = p.mean(axis=0)
    p -= centre

    # Core pull: high degree sinks toward the centre, low degree drifts to the arms.
    deg = np.array([n["deg"] for n in nodes], dtype=float)
    dnorm = deg / deg.max()
    scale = 0.30 + 0.95 * (1.0 - dnorm) ** 1.4
    p *= scale[:, None]

    # Cluster (community) for colour.
    try:
        comms = nx.community.greedy_modularity_communities(G, weight="weight")
    except Exception:
        comms = []
    cluster = {}
    for i, c in enumerate(comms):
        for name in c:
            cluster[name] = i
    return G, {n["name"]: p[i] for i, n in enumerate(nodes)}, cluster


def _starfield(ax, xlim, ylim, n, rng):
    sx = rng.uniform(xlim[0], xlim[1], n)
    sy = rng.uniform(ylim[0], ylim[1], n)
    ax.scatter(sx, sy, s=rng.uniform(0.2, 1.6, n), color="white",
               alpha=rng.uniform(0.05, 0.5, n), zorder=1, edgecolors="none")


def _legend(ax, title: str):
    """A compact corner key: size = times named, colour = cluster, line = co-mention."""
    tx = ax.transAxes
    ax.add_patch(Rectangle((0.022, 0.022), 0.40, 0.20, transform=tx,
                           facecolor="#070a16", edgecolor="#39507a", alpha=0.6,
                           linewidth=0.7, zorder=8))
    ax.text(0.04, 0.195, title, transform=tx, color="white", fontsize=11,
            fontweight="bold", va="center", zorder=9, alpha=0.95)
    # size
    ax.scatter([0.052], [0.150], s=14, c="white", transform=tx, zorder=9, edgecolors="none")
    ax.scatter([0.082], [0.150], s=90, c="white", transform=tx, zorder=9, edgecolors="none")
    ax.text(0.12, 0.150, "size  =  how often the entity is named", transform=tx,
            color="#dde4f5", fontsize=9, va="center", zorder=9)
    # colour
    for i, cx in enumerate((0.045, 0.063, 0.081)):
        ax.scatter([cx], [0.103], s=55, c=[PALETTE[i]], transform=tx, zorder=9,
                   edgecolors="none")
    ax.text(0.12, 0.103, "colour  =  cluster (who groups together)", transform=tx,
            color="#dde4f5", fontsize=9, va="center", zorder=9)
    # line
    ax.plot([0.045, 0.092], [0.058, 0.058], color="#6fb4e0", transform=tx, zorder=9,
            linewidth=1.4)
    ax.text(0.12, 0.058, "line  =  named together in one claim", transform=tx,
            color="#dde4f5", fontsize=9, va="center", zorder=9)


def _render(G, pos, nodes, cluster, figsize, xlim, ylim, hubs, out: Path, labels: bool,
            legend: bool):
    deg = {n["name"]: n["deg"] for n in nodes}
    dmax = max(deg.values()) or 1
    span = xlim[1] - xlim[0]
    fig, ax = plt.subplots(figsize=figsize)
    fig.patch.set_facecolor(BG)
    ax.set_facecolor(BG)
    rng = np.random.default_rng(11)

    # Nebula: large soft colour clouds.
    for col, (rx, ry), rs in NEBULA:
        ax.scatter([xlim[0] + (rx + 0.5) * span], [ylim[0] + (ry + 0.5) * (ylim[1] - ylim[0])],
                   s=(span * 1600 * rs) ** 1.0 * 900, color=[col], alpha=0.16,
                   zorder=0, edgecolors="none")
    _starfield(ax, xlim, ylim, 2200, rng)

    # Filaments: faint, only the stronger ties, so it reads as structure not clutter.
    ews = sorted(G.edges(data=True), key=lambda e: e[2]["weight"], reverse=True)
    for u, v, d in ews[: min(len(ews), 1400)]:
        x1, y1 = pos[u]; x2, y2 = pos[v]
        a = min(0.04 + d["weight"] * 0.015, 0.16)
        ax.plot([x1, x2], [y1, y2], color="#6fb4e0", alpha=a, linewidth=0.35, zorder=2)

    # Claim dust: a soft halo around each node, denser for the hubs.
    for n in nodes:
        x, y = pos[n["name"]]
        frac = deg[n["name"]] / dmax
        k = int(5 + 34 * math.sqrt(frac))
        spread = (0.010 + 0.045 * math.sqrt(frac)) * span * 1.4
        dx = rng.normal(x, spread, k); dy = rng.normal(y, spread, k)
        col = PALETTE[cluster.get(n["name"], 0) % len(PALETTE)]
        ax.scatter(dx, dy, s=rng.uniform(0.4, 3.2, k), color=[col],
                   alpha=0.16, zorder=3, edgecolors="none")

    # Nodes with layered bloom.
    xs = np.array([pos[n["name"]][0] for n in nodes])
    ys = np.array([pos[n["name"]][1] for n in nodes])
    cols = np.array([PALETTE[cluster.get(n["name"], 0) % len(PALETTE)] for n in nodes])
    base = np.array([16 + 620 * (deg[n["name"]] / dmax) ** 0.85 for n in nodes])
    for mult, alpha in ((9.0, 0.05), (4.0, 0.10), (1.8, 0.20)):
        ax.scatter(xs, ys, s=base * mult, c=cols, alpha=alpha, zorder=4, edgecolors="none")
    ax.scatter(xs, ys, s=base, c=cols, alpha=0.97, zorder=5, edgecolors="none")
    big = base > base.max() * 0.4
    ax.scatter(xs[big], ys[big], s=base[big] * 0.30, c="white", alpha=0.92, zorder=6,
               edgecolors="none")

    # Hub labels (opt-in; off by default for a clean hero image).
    if labels:
        for n in nodes:
            if any(h.lower() in n["name"].lower() for h in hubs) and deg[n["name"]] > dmax * 0.10:
                x, y = pos[n["name"]]
                if xlim[0] < x < xlim[1] and ylim[0] < y < ylim[1]:
                    ax.text(x, y + 0.018 * span, n["name"], color="white", fontsize=8.5,
                            ha="center", va="bottom", alpha=0.9, zorder=7, fontweight="medium")

    if legend:
        _legend(ax, "Madlanga evidence graph")

    ax.set_xlim(*xlim); ax.set_ylim(*ylim)
    ax.set_aspect("equal"); ax.axis("off")
    fig.subplots_adjust(left=0, right=1, top=1, bottom=0)
    OUT.mkdir(parents=True, exist_ok=True)
    fig.savefig(out, dpi=220, facecolor=fig.get_facecolor())
    plt.close(fig)
    print(f"wrote {out}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--top", type=int, default=900, help="Most-connected entities to plot.")
    ap.add_argument("--seed", type=int, default=5)
    ap.add_argument("--hubs", nargs="*", default=DEFAULT_HUBS)
    ap.add_argument("--labels", action="store_true",
                    help="Caption the hub nodes (off by default for a clean hero image).")
    ap.add_argument("--legend", action="store_true",
                    help="Draw a corner key: size / colour / line meanings.")
    args = ap.parse_args()

    nodes, edges = fetch(args.top)
    if not nodes:
        raise SystemExit("No entities returned. Is Neo4j up with claims loaded?")
    print(f"galaxy: {len(nodes)} nodes, {len(edges)} edges")
    G, pos, cluster = layout(nodes, edges, args.seed)

    xs = np.array([p[0] for p in pos.values()])
    ys = np.array([p[1] for p in pos.values()])
    r = 1.04 * max(np.percentile(np.abs(xs), 99), np.percentile(np.abs(ys), 99))

    _render(G, pos, nodes, cluster, (10, 10), (-r, r), (-r, r), args.hubs,
            OUT / "graph_galaxy_square.png", args.labels, args.legend)
    rw = r * 1.3
    rh = rw * (1 / 1.9)
    _render(G, pos, nodes, cluster, (19, 10), (-rw, rw), (-rh, rh), args.hubs,
            OUT / "graph_galaxy_wide.png", args.labels, args.legend)


if __name__ == "__main__":
    main()
