"""Version 4: more logo/name spacing and heavier numeral strokes."""
from pathlib import Path
import ast
import collections
import io
import json
import zipfile
import xml.etree.ElementTree as E
import numpy as np
import mapbox_earcut as earcut
from PIL import Image, ImageDraw
from shapely import affinity
from shapely.geometry import Polygon
from shapely.geometry.polygon import orient
from shapely.ops import unary_union

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / 'output'
NS = 'http://schemas.microsoft.com/3dmanufacturing/core/2015/02'
T = lambda n: '{' + NS + '}' + n
BASE = 3.4289999
TOP = 4.491002442
E.register_namespace('', NS)
E.register_namespace('p', 'http://schemas.microsoft.com/3dmanufacturing/production/2015/06')

# Load only shared geometry/preview helpers; previous builders must not run.
for source, names in [('build_larger.py', ['pieces', 'clean', 'extrude', 'setmesh', 'render']),
                      ('enlarge_logo.py', ['mesh', 'footprint'])]:
    tree = ast.parse((ROOT / 'personalized' / source).read_text())
    nodes = [n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name in names]
    exec(compile(ast.Module(body=nodes, type_ignores=[]), source, 'exec'))

artifacts = []
previews = []
report = []
for who in ['SOPHIA_43', 'JASON_4']:
    source = OUT / f'EIE_{who}_v3_PLA.3mf'
    with zipfile.ZipFile(source) as z:
        files = {n: z.read(n) for n in z.namelist()}
    model = E.fromstring(files['3D/Objects/object_1.model'])
    main = E.fromstring(files['3D/3dmodel.model'])
    settings = E.fromstring(files['Metadata/model_settings.config'])
    objects = {o.get('id'): o for o in model.findall('.//' + T('object'))}
    old = {k: mesh(o) for k, o in objects.items()}
    for comp in main.findall('.//' + T('component')):
        assert comp.get('transform') == '1 0 0 0 1 0 0 0 1 0 0 0'

    # Move both name colours together by 3 mm.
    for key in ['2', '10']:
        for vertex in objects[key].findall('.//' + T('vertex')):
            vertex.set('x', format(float(vertex.get('x')) + 3 / 1.2, '.12g'))

    old_white = footprint(*old['3'])
    white = affinity.translate(old_white.buffer(.35, join_style=2), yoff=3.5)
    outline = white.buffer(.6, join_style=2).difference(white)
    # Keep all digits separate and preserve their internal openings.
    assert len(pieces(old_white)) == len(pieces(white))
    assert sum(len(p.interiors) for p in pieces(old_white)) == sum(len(p.interiors) for p in pieces(white))
    for key, shape in [('3', white), ('11', outline)]:
        v, t = extrude(shape)
        setmesh(model, key, v, t)
        settings.find(f".//part[@id='{key}']/mesh_stat").set('face_count', str(len(t)))
    settings.find("object/metadata[@face_count]").set('face_count', str(len(model.findall('.//' + T('triangle')))))

    new = {o.get('id'): mesh(o) for o in model.findall('.//' + T('object'))}
    for key in ['1', '5', '6', '7', '8', '9']:
        assert np.array_equal(new[key][0], old[key][0])
        assert np.array_equal(new[key][1], old[key][1])
    before = np.concatenate([v for v, t in old.values()])
    after = np.concatenate([v for v, t in new.values()])
    assert np.allclose(before.min(axis=0), after.min(axis=0), atol=1e-8)
    assert np.allclose(before.max(axis=0), after.max(axis=0), atol=1e-8)
    shapes = {k: footprint(*data) for k, data in new.items()}
    logo = unary_union([shapes[k] for k in ['6', '7', '8', '9']])
    name = shapes['2'].union(shapes['10'])
    number = shapes['3'].union(shapes['11'])
    old_name = footprint(*old['2']).union(footprint(*old['10']))
    assert logo.distance(name) > logo.distance(old_name) + 2.5
    assert name.distance(number) > 3
    assert number.distance(shapes['5']) > 3
    decoration = unary_union([logo, name, number])
    assert decoration.difference(shapes['1']).area < 1e-8
    assert decoration.intersection(shapes['5']).area < 1e-8
    assert shapes['3'].intersection(shapes['11']).area < 1e-8
    assert shapes['3'].area > old_white.area * 1.08
    assert json.loads(files['Metadata/project_settings.config'])['filament_type'] == ['PLA'] * 4

    stem = f'EIE_{who}_v4_PLA'
    preview = OUT / f'{stem}_Vorschau.png'
    im, png = render(model, main, preview)
    previews.append(im)
    for n in files:
        if n.endswith('.png'):
            files[n] = png
    for n, root in [('3D/Objects/object_1.model', model), ('Metadata/model_settings.config', settings)]:
        files[n] = E.tostring(root, encoding='utf-8', xml_declaration=True)
    target = OUT / f'{stem}.3mf'
    with zipfile.ZipFile(target, 'w', zipfile.ZIP_DEFLATED) as z:
        for n, data in files.items():
            z.writestr(n, data)
    with zipfile.ZipFile(target) as z, zipfile.ZipFile(source) as src:
        assert z.testzip() is None
        assert z.read('Metadata/project_settings.config') == src.read('Metadata/project_settings.config')
        assert z.read('3D/3dmodel.model') == src.read('3D/3dmodel.model')
    result = {'tag': who, 'logo_to_name_before_mm': round(logo.distance(old_name), 3),
              'logo_to_name_after_mm': round(logo.distance(name), 3),
              'name_to_number_mm': round(name.distance(number), 3),
              'number_to_frame_mm': round(number.distance(shapes['5']), 3),
              'numeral_white_area_increase_percent': round(100 * (shapes['3'].area / old_white.area - 1), 1)}
    print(result)
    report.append(result)
    artifacts.extend([target, preview])

comparison = Image.new('RGB', (1500, 1300), '#e9edf0')
for i, im in enumerate(previews):
    comparison.paste(im, (750 * i, 0))
preview = OUT / 'SOPHIA_43_JASON_4_v4_PLA_Vorschau.png'
comparison.save(preview)
artifacts.append(preview)
readme = OUT / 'Anleitung_SOPHIA_JASON_v4_PLA.txt'
readme.write_text('''EIE HOCKEY BAG TAGS – SOPHIA 43 UND JASON 4 – VERSION 4 – PLA

Gegenüber Version 3:
- Name 3 mm weiter nach unten, für mehr Abstand zum Logo.
- Nummer 3,5 mm weiter nach unten.
- Weisse Ziffernkontur zusätzlich um 0,35 mm nach aussen erweitert:
  gerade Striche dadurch rund 0,7 mm breiter. Gelbe Kontur weiterhin 0,6 mm.
- Vergrössertes Logo, Namensschrift, Farben, Befestigungsschlitz und Grundform unverändert.

Abmessungen je Anhänger: 55,88 × 106,68 mm; maximale Gesamtdicke 3,96 mm.
Name und Nummer sind feste Geometrie, nicht mit dem Textwerkzeug parametrierbar.
Vorschau mit der bisherigen Entwurfsfarbe; grüne Filamentmarke noch nicht festgelegt.

Die gewünschte 3MF als Projekt in Bambu Studio öffnen.
Vorhandenes Profil: Bambu Lab A1, 0,4-mm-Düse, Generic PLA für alle vier Farben.
Filamente: 1 Weiss, 2 Grün, 3 Gelb, 4 Schwarz.
Passende Profile für die tatsächlichen Rollen auswählen, Spülmengen neu berechnen,
neu slicen und die Schichtvorschau prüfen.

Geometrisch geprüft: unveränderte Aussenmasse und Dicke, geschlossene neue
Ziffernflächen, erhaltene Ziffernöffnungen sowie Abstände zu Logo, Name und Rahmen.
Bambu-Studio-Import, Slicing und Probedruck wurden hier nicht durchgeführt.

Schriftgrundlage: College und College Bold von Matthew Welch.
https://squaregear.net/fonts/college.html
Schriftlizenz beigefügt; ursprüngliche Lizenzmetadaten in den Projekten erhalten.
''')
artifacts.extend([readme, ROOT / 'fonts/college/license.txt'])
with zipfile.ZipFile(OUT / 'EIE_SOPHIA_43_JASON_4_v4_PLA_Paket.zip', 'w', zipfile.ZIP_DEFLATED) as z:
    for path in artifacts:
        z.write(path, path.name)
(OUT / 'Pruefung_v4_PLA.json').write_text(json.dumps(report, indent=2))
