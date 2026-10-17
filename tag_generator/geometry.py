"""Mesh operations in the approved tag's coordinate system.

Face coordinates are millimetres (right, down). The inherited 3MF build
transform scales model X by 1.2, Y by 0.5 (depth), Z by 1.1.
"""
from pathlib import Path
import collections
import io
import numpy as np
import mapbox_earcut as earcut
from shapely.geometry import Polygon
from shapely.geometry.polygon import orient
from shapely.ops import unary_union
from PIL import Image, ImageDraw
import xml.etree.ElementTree as E
NS = 'http://schemas.microsoft.com/3dmanufacturing/core/2015/02'
T = lambda n: '{' + NS + '}' + n
BASE = 3.4289999
TOP = 4.491002442

def pieces(p):
    if isinstance(p, Polygon):
        return [p]
    return [q for a in p.geoms for q in pieces(a)]

def clean(r):
    pts = list(r.coords)[:-1]
    while True:
        new = []
        for i, b in enumerate(pts):
            a = pts[i - 1]
            c = pts[(i + 1) % len(pts)]
            if abs((b[0] - a[0]) * (c[1] - b[1]) - (b[1] - a[1]) * (c[0] - b[0])) > 1e-10:
                new.append(b)
        if len(new) == len(pts):
            return new
        assert len(new) >= 3
        pts = new

def extrude(shape, *, base=BASE, top=TOP):
    vertices = []
    triangles = []
    for poly in pieces(shape.buffer(-0.0001, join_style=2)):
        poly = orient(poly, sign=1)
        rings = [clean(poly.exterior)] + [clean(r) for r in poly.interiors]
        coords = np.array([p for r in rings for p in r])
        n = len(coords)
        start = len(vertices)
        faces = earcut.triangulate_float64(coords, np.cumsum([len(r) for r in rings], dtype=np.uint32)).reshape(-1, 3)
        local = []
        cap_edges = []
        cap_area = 0
        for h in [base, top]:
            vertices.extend(((y / 1.2, h, -x / 1.1) for x, y in coords))
        for a, b, c in faces:
            u = coords[b] - coords[a]
            v = coords[c] - coords[a]
            if u[0] * v[1] - u[1] * v[0] < 0:
                b, c = (c, b)
            local.extend([(int(a), int(c), int(b)), (int(a + n), int(b + n), int(c + n))])
            cap_edges.extend([(int(a), int(b)), (int(b), int(c)), (int(c), int(a))])
            cap_area += abs(u[0] * v[1] - u[1] * v[0]) / 2
        assert abs(cap_area - poly.area) < 1e-07
        counts = collections.Counter((tuple(sorted(e)) for e in cap_edges))
        for a, b in cap_edges:
            if counts[tuple(sorted((a, b)))] == 1:
                local.extend([(a, b, b + n), (a, b + n, a + n)])
        triangles.extend(((start + a, start + c, start + b) for a, b, c in local))
    edges = collections.Counter((tuple(sorted((a, b))) for t in triangles for a, b in zip(t, (t[1], t[2], t[0]))))
    assert all((n == 2 for n in edges.values())), 'Mesh edge error'
    volume = sum((sum((vertices[a][k] * (vertices[b][(k + 1) % 3] * vertices[c][(k + 2) % 3] - vertices[b][(k + 2) % 3] * vertices[c][(k + 1) % 3]) for k in range(3))) for a, b, c in triangles)) / 6
    assert volume > 0
    return (vertices, triangles)

def setmesh(model, key, v, t):
    o = model.find('.//' + T('object') + f"[@id='{key}']")
    if o is None:
        o = E.SubElement(model.find(T('resources')), T('object'), {'id': key, 'type': 'model'})
    else:
        o.remove(o.find(T('mesh')))
    mesh = E.SubElement(o, T('mesh'))
    vr = E.SubElement(mesh, T('vertices'))
    tr = E.SubElement(mesh, T('triangles'))
    for p in v:
        E.SubElement(vr, T('vertex'), {a: format(float(n), '.12g') for a, n in zip(('x', 'y', 'z'), p)})
    for p in t:
        E.SubElement(tr, T('triangle'), {a: str(n) for a, n in zip(('v1', 'v2', 'v3'), p)})

def render(model, main, path):
    objects = {o.get('id'): o for o in model.findall('.//' + T('object'))}
    palette = {'1': '#123E2B', '2': '#FFFFFF', '3': '#FFFFFF', '5': '#F4BE19', '6': '#101010', '7': '#FFFFFF', '8': '#123E2B', '9': '#F4BE19', '10': '#F4BE19', '11': '#F4BE19'}
    im = Image.new('RGB', (1500, 2600), '#e9edf0')
    d = ImageDraw.Draw(im)
    faces = []
    for comp in main.findall('.//' + T('component')):
        key = comp.get('objectid')
        o = objects[key]
        m = np.array(list(map(float, comp.get('transform').split())))
        v = np.array([[float(v.get(a)) for a in ('x', 'y', 'z')] for v in o.findall('.//' + T('vertex'))])
        v = v @ m[:9].reshape(3, 3) + m[9:]
        for t in o.findall('.//' + T('triangle')):
            points = v[[int(t.get(a)) for a in ('v1', 'v2', 'v3')]]
            faces.append((sum((p[1] for p in points)), [(750 - p[2] * 1.1 * 21, 1300 + p[0] * 1.2 * 21) for p in points], palette[key]))
    for _, pts, color in sorted(faces, key=lambda a: a[0]):
        d.polygon(pts, fill=color)
    im = im.resize((750, 1300), Image.Resampling.LANCZOS)
    im.save(path)
    buf = io.BytesIO()
    im.save(buf, format='PNG')
    return (im, buf.getvalue())

def mesh(obj):
    v = np.array([[float(p.get(a)) for a in ('x', 'y', 'z')] for p in obj.findall('.//' + T('vertex'))])
    t = np.array([[int(p.get(a)) for a in ('v1', 'v2', 'v3')] for p in obj.findall('.//' + T('triangle'))])
    return (v, t)

def footprint(v, t):
    polygons = [Polygon(v[tri][:, [2, 0]] * [-1.1, 1.2]) for tri in t]
    return unary_union([p for p in polygons if p.area > 1e-10])
