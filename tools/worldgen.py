#!/usr/bin/env python3
"""Turn Natural Earth 110m country outlines into ready-made SVG paths.

Input is the world-atlas TopoJSON (public-domain Natural Earth data); output is
data/world.json: one path string per country, already projected, so the page
needs no projection library and no tile server.

    python3 -I tools/worldgen.py <countries-110m.json>

Projection is plate carree (lon,lat straight to x,y), which is what lets the
page place a pin from coordinates with two multiplications. The canvas is
W x H units covering the whole globe; the page crops the polar emptiness with
its viewBox.
"""
import json, os, sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
W, H = 2000.0, 1000.0          # x: -180..180, y: 90..-90
MIN_AREA = 0.6                 # drop specks smaller than this (units squared)


def decode_arcs(topo):
    """TopoJSON quantised, delta-encoded arcs -> lists of [lon, lat]."""
    sx, sy = topo["transform"]["scale"]
    tx, ty = topo["transform"]["translate"]
    out = []
    for arc in topo["arcs"]:
        x = y = 0
        pts = []
        for dx, dy in arc:
            x += dx
            y += dy
            pts.append((x * sx + tx, y * sy + ty))
        out.append(pts)
    return out


def ring_points(arcs, idxs):
    pts = []
    for i in idxs:
        if i < 0:
            seg = arcs[~i][::-1]
        else:
            seg = arcs[i]
        if pts and pts[-1] == seg[0]:
            pts.extend(seg[1:])
        else:
            pts.extend(seg)
    return pts


def project(pt):
    lon, lat = pt
    return ((lon + 180.0) / 360.0 * W, (90.0 - lat) / 180.0 * H)


def area(ring):
    a = 0.0
    for i in range(len(ring)):
        x1, y1 = ring[i]
        x2, y2 = ring[(i + 1) % len(ring)]
        a += x1 * y2 - x2 * y1
    return abs(a) / 2.0


def simplify(ring, tol=0.35):
    """Drop points that sit within tol of the previous kept point."""
    out = [ring[0]]
    for p in ring[1:-1]:
        if abs(p[0] - out[-1][0]) + abs(p[1] - out[-1][1]) >= tol:
            out.append(p)
    out.append(ring[-1])
    return out if len(out) >= 4 else ring


def path_for(geom, arcs):
    polys = geom["arcs"] if geom["type"] == "MultiPolygon" else [geom["arcs"]]
    d = []
    for poly in polys:
        for ring in poly:
            pts = [project(p) for p in ring_points(arcs, ring)]
            if len(pts) < 4 or area(pts) < MIN_AREA:
                continue
            pts = simplify(pts)
            # The dateline: a ring that wraps the whole canvas is Antarctica or
            # Russia split by the source data already, so no stitching needed.
            d.append("M" + "L".join("%.1f %.1f" % p for p in pts) + "Z")
    return "".join(d)


def main():
    src = sys.argv[1]
    topo = json.load(open(src))
    arcs = decode_arcs(topo)
    out = []
    for geom in topo["objects"]["countries"]["geometries"]:
        name = (geom.get("properties") or {}).get("name") or geom.get("id")
        d = path_for(geom, arcs)
        if d:
            out.append({"n": name, "d": d})
    out.sort(key=lambda c: c["n"])
    path = os.path.join(ROOT, "data", "world.json")
    with open(path, "w") as fh:
        json.dump({"w": W, "h": H, "countries": out}, fh, separators=(",", ":"))
    print("wrote %s: %d countries, %d KB" % (path, len(out), os.path.getsize(path) // 1024))


if __name__ == "__main__":
    main()
