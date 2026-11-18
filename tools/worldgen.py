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
import json, math, os, re, sys

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


def unwrap(pts):
    """A ring that crosses the dateline jumps most of the canvas in one step.
    Undo the jumps so the ring is continuous, even if that puts it outside
    0..W."""
    out, off = [pts[0]], 0.0
    for i in range(1, len(pts)):
        dx = pts[i][0] - pts[i - 1][0]
        if dx > W / 2:
            off -= W
        elif dx < -W / 2:
            off += W
        out.append((pts[i][0] + off, pts[i][1]))
    return out


def clip_strip(ring, lo, hi):
    """Sutherland-Hodgman against the two vertical edges of the canvas."""
    def half(r, inside, cut):
        out = []
        for i in range(len(r)):
            a, b = r[i], r[(i + 1) % len(r)]
            ia, ib = inside(a), inside(b)
            if ia:
                out.append(a)
                if not ib:
                    out.append(cut(a, b))
            elif ib:
                out.append(cut(a, b))
        return out

    def at(a, b, x):
        t = (x - a[0]) / (b[0] - a[0])
        return (x, a[1] + t * (b[1] - a[1]))

    r = half(ring, lambda p: p[0] >= lo, lambda a, b: at(a, b, lo))
    if not r:
        return []
    return half(r, lambda p: p[0] <= hi, lambda a, b: at(a, b, hi))


def split_dateline(pts):
    """Russia, Fiji and Antarctica each have a ring that runs off one side of
    the world and back on the other. Projected, that ring stretches across the
    entire canvas as a band — which the land layer has always drawn and which
    became obvious once culture areas were shaded in. Cut the ring at the
    canvas edges and keep each side as its own piece."""
    if all(abs(pts[i][0] - pts[i - 1][0]) <= W / 2 for i in range(1, len(pts))):
        return [pts]
    u = unwrap(pts)
    xs = [p[0] for p in u]
    pieces = []
    k = int(math.floor(min(xs) / W))
    while k * W < max(xs):
        shifted = [(x - k * W, y) for x, y in u]
        c = clip_strip(shifted, 0.0, W)
        if len(c) >= 4 and area(c) >= MIN_AREA:
            pieces.append(c)
        k += 1
    return pieces


def path_for(geom, arcs):
    polys = geom["arcs"] if geom["type"] == "MultiPolygon" else [geom["arcs"]]
    d = []
    for poly in polys:
        for ring in poly:
            pts = [project(p) for p in ring_points(arcs, ring)]
            if len(pts) < 4 or area(pts) < MIN_AREA:
                continue
            pts = simplify(pts)
            for piece in split_dateline(pts):
                d.append("M" + "L".join("%.1f %.1f" % p for p in piece) + "Z")
    return "".join(d)


def refit():
    """Re-cut data/world.json in place, through the same code the generator
    uses, so the file on disk and a future regeneration cannot disagree."""
    path = os.path.join(ROOT, "data", "world.json")
    world = json.load(open(path))
    fixed = 0
    for c in world["countries"]:
        out = []
        for sp in c["d"].split("M"):
            sp = sp.strip()
            if not sp:
                continue
            n = [float(v) for v in re.findall(r"-?\d+\.?\d*", sp)]
            pts = list(zip(n[0::2], n[1::2]))
            pieces = split_dateline(pts)
            if len(pieces) != 1:
                fixed += 1
            for piece in pieces:
                out.append("M" + "L".join("%.1f %.1f" % p for p in piece) + "Z")
        c["d"] = "".join(out)
    with open(path, "w") as fh:
        json.dump(world, fh, separators=(",", ":"))
    print("re-cut %s: %d wrapped rings split, %d KB"
          % (path, fixed, os.path.getsize(path) // 1024))


def main():
    if len(sys.argv) > 1 and sys.argv[1] == "--refit":
        return refit()
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
