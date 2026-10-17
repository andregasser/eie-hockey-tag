"""Create version 3 from the approved PLA projects, preserving print settings."""
from pathlib import Path
import ast
import collections
import io
import json
import zipfile
import xml.etree.ElementTree as E

import numpy as np
from PIL import Image, ImageDraw
from shapely.geometry import Polygon
from shapely.ops import unary_union

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / 'output'
NS = 'http://schemas.microsoft.com/3dmanufacturing/core/2015/02'
T = lambda n: '{' + NS + '}' + n
E.register_namespace('', NS)
E.register_namespace('p', 'http://schemas.microsoft.com/3dmanufacturing/production/2015/06')
SCALE = 1.4
DOWN = 8.0

# Reuse the established triangle-based preview, without running the v2 builder.
tree = ast.parse((ROOT / 'personalized/build_larger.py').read_text())
render_node = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == 'render')
exec(compile(ast.Module(body=[render_node], type_ignores=[]), '<preview>', 'exec'))


def mesh(obj):
    v = np.array([[float(p.get(a)) for a in ('x', 'y', 'z')]
                  for p in obj.findall('.//' + T('vertex'))])
    t = np.array([[int(p.get(a)) for a in ('v1', 'v2', 'v3')]
                  for p in obj.findall('.//' + T('triangle'))])
    return v, t


def footprint(v, t):
    polygons = [Polygon(v[tri][:, [2, 0]] * [-1.1, 1.2]) for tri in t]
    return unary_union([p for p in polygons if p.area > 1e-10])


previews = []
artifacts = []
report = []
for who in ['SOPHIA_43', 'JASON_4']:
    with zipfile.ZipFile(OUT / f'EIE_{who}_v2_PLA.3mf') as z:
        files = {n: z.read(n) for n in z.namelist()}
    model = E.fromstring(files['3D/Objects/object_1.model'])
    main = E.fromstring(files['3D/3dmodel.model'])
    objects = {o.get('id'): o for o in model.findall('.//' + T('object'))}
    old = {key: mesh(o) for key, o in objects.items()}
    for c in main.findall('.//' + T('component')):
        assert c.get('transform') == '1 0 0 0 1 0 0 0 1 0 0 0'
    logo_vertices = np.concatenate([old[k][0] for k in ['6', '7', '8', '9']])
    top = logo_vertices[:, 0].min()
    centre = (logo_vertices[:, 2].min() + logo_vertices[:, 2].max()) / 2
    for key, obj in objects.items():
        for p in obj.findall('.//' + T('vertex')):
            if key in ['6', '7', '8', '9']:
                p.set('x', format(top + SCALE * (float(p.get('x')) - top), '.12g'))
                p.set('z', format(centre + SCALE * (float(p.get('z')) - centre), '.12g'))
            elif key in ['2', '3', '10', '11']:
                p.set('x', format(float(p.get('x')) + DOWN / 1.2, '.12g'))
    new = {key: mesh(o) for key, o in objects.items()}
    for key in ['1', '5']:
        assert np.array_equal(old[key][0], new[key][0])
    for key, (v, t) in new.items():
        assert np.array_equal(old[key][1], t)
        assert np.array_equal(old[key][0][:, 1], v[:, 1])  # extrusion unchanged
        if key in ['6', '7', '8', '9', '2', '3', '10', '11']:
            edges = collections.Counter(tuple(sorted((a, b))) for tri in t
                                        for a, b in zip(tri, np.roll(tri, -1)))
            assert all(n == 2 for n in edges.values())
            assert np.einsum('ij,ij->i', v[t[:, 0]], np.cross(v[t[:, 1]], v[t[:, 2]])).sum() > 0
    before = np.concatenate([v for v, t in old.values()])
    after = np.concatenate([v for v, t in new.values()])
    assert np.allclose(before.min(axis=0), after.min(axis=0))
    assert np.allclose(before.max(axis=0), after.max(axis=0))
    shapes = {key: footprint(*data) for key, data in new.items()}
    logo = unary_union([shapes[k] for k in ['6', '7', '8', '9']])
    name = unary_union([shapes[k] for k in ['2', '10']])
    number = unary_union([shapes[k] for k in ['3', '11']])
    decoration = unary_union([logo, name, number])
    assert decoration.difference(shapes['1']).area < 1e-8  # includes slot clearance
    assert decoration.intersection(shapes['5']).area < 1e-8
    assert logo.distance(name) > 2
    assert name.distance(number) > 3
    assert number.distance(shapes['5']) > 3
    assert shapes['5'].bounds[3] - number.bounds[3] > 10
    cfg = json.loads(files['Metadata/project_settings.config'])
    assert cfg['filament_type'] == ['PLA'] * 4
    files['3D/Objects/object_1.model'] = E.tostring(model, encoding='utf-8', xml_declaration=True)
    stem = f'EIE_{who}_v3_PLA'
    preview_path = OUT / f'{stem}_Vorschau.png'
    im, png = render(model, main, preview_path)
    previews.append(im)
    for n in files:
        if n.endswith('.png'):
            files[n] = png
    target = OUT / f'{stem}.3mf'
    with zipfile.ZipFile(target, 'w', zipfile.ZIP_DEFLATED) as z:
        for n, data in files.items():
            z.writestr(n, data)
    with zipfile.ZipFile(target) as z, zipfile.ZipFile(OUT / f'EIE_{who}_v2_PLA.3mf') as src:
        assert z.testzip() is None
        for n in ['Metadata/project_settings.config', 'Metadata/model_settings.config', '3D/3dmodel.model']:
            assert z.read(n) == src.read(n)
    result = {'tag': who, 'logo_width_mm': round(logo.bounds[2] - logo.bounds[0], 3),
              'logo_height_mm': round(logo.bounds[3] - logo.bounds[1], 3),
              'logo_to_name_mm': round(logo.distance(name), 3),
              'number_to_frame_mm': round(number.distance(shapes['5']), 3)}
    report.append(result)
    print(result)
    artifacts.extend([target, preview_path])

comparison = Image.new('RGB', (1500, 1300), '#e9edf0')
for i, im in enumerate(previews):
    comparison.paste(im, (750 * i, 0))
preview_path = OUT / 'SOPHIA_43_JASON_4_v3_PLA_Vorschau.png'
comparison.save(preview_path)
artifacts.append(preview_path)
readme = OUT / 'Anleitung_SOPHIA_JASON_v3_PLA.txt'
readme.write_text('''EIE HOCKEY BAG TAGS – SOPHIA 43 UND JASON 4 – VERSION 3 – PLA

Logo gegenüber Version 2 in Breite und Höhe um 40 % vergrössert.
Neue Logogrösse: ca. 30,47 × 31,04 mm. Oberkante bleibt gleich.
Name und Nummer jeweils um 8 mm nach unten verschoben.
Schriftgrösse, Schriftstärke, Farben, Befestigungsschlitz und Aussenmasse unverändert.
Abmessungen je Anhänger: 55,88 × 106,68 mm; maximale Gesamtdicke 3,96 mm.

Die 3MF-Dateien als Projekte in Bambu Studio öffnen.
Vorhandenes Profil: Bambu Lab A1, 0,4-mm-Düse, Generic PLA für alle vier Farben.
Filamente: 1 Weiss, 2 Grün, 3 Gelb, 4 Schwarz.
Profile der tatsächlich verwendeten Rollen auswählen, Spülmengen neu berechnen und neu slicen.
Die grüne Filamentmarke ist noch nicht festgelegt; die Vorschau zeigt die bisherige Entwurfsfarbe.
Name und Nummer sind feste Geometrie und nicht mit dem Textwerkzeug parametrierbar.

Geometrisch geprüft: unveränderte Aussenmasse und Dicke, geschlossene veränderte
Bauteile, vollständige Auflage und Abstände zwischen Logo, Schrift und Rahmen.
Bambu-Studio-Import, Slicing und Probedruck wurden hier nicht durchgeführt.

Schriftgrundlage: College und College Bold von Matthew Welch.
https://squaregear.net/fonts/college.html
Die beigefügte Schriftlizenz sowie die ursprünglichen Lizenzmetadaten bleiben erhalten.
''')
artifacts.extend([readme, ROOT / 'fonts/college/license.txt'])
with zipfile.ZipFile(OUT / 'EIE_SOPHIA_43_JASON_4_v3_PLA_Paket.zip', 'w', zipfile.ZIP_DEFLATED) as z:
    for path in artifacts:
        z.write(path, path.name)
(OUT / 'Pruefung_v3_PLA.json').write_text(json.dumps(report, indent=2))
