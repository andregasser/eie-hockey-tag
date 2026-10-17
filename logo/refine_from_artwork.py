"""Rebuild the v5 logo from supplied transparent artwork, preserving v4 text.

Run from the project root: python -m logo.refine_from_artwork
No photograph thresholding, perspective distortion, or added colours.
"""
from pathlib import Path
import json
import shutil
import zipfile
import xml.etree.ElementTree as ET

import numpy as np
from PIL import Image
from shapely import affinity
from shapely.geometry import Polygon, box
from shapely.ops import unary_union

from tag_generator.geometry import T, NS, extrude, footprint, mesh, render, setmesh

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / 'output'
SOURCE = ROOT / 'logo/sources/eie-logo-puck.png'
PALETTE = {'6': '#101010', '7': '#FFFFFF', '8': '#123E2B', '9': '#F4BE19'}
ET.register_namespace('', NS)
ET.register_namespace('p', 'http://schemas.microsoft.com/3dmanufacturing/production/2015/06')


def polygons(shape):
    if isinstance(shape, Polygon):
        return [shape] if not shape.is_empty else []
    return [p for g in getattr(shape, 'geoms', []) for p in polygons(g)]


def pixel_region(mask):
    # Contiguous runs share their exact boundaries, with no one-pixel gaps.
    rectangles = []
    for y, row in enumerate(mask):
        edges = np.flatnonzero(np.diff(np.pad(row.astype(np.int8), (1, 1))))
        rectangles.extend(box(int(a), y, int(b), y + 1) for a, b in edges.reshape(-1, 2))
    return unary_union(rectangles)


def trace_artwork(target_bounds):
    rgba = np.asarray(Image.open(SOURCE).convert('RGBA'))
    opaque = rgba[:, :, 3] >= 128
    rgb = rgba[:, :, :3].astype(float)
    # Source dark shadows and charcoal outlines share the black filament.
    swatches = np.array([[35, 31, 32], [255, 255, 255], [0, 71, 49], [250, 201, 30]])
    labels = np.square(rgb[:, :, None, :] - swatches).sum(axis=3).argmin(axis=2)
    # Grey antialiasing between white letters and black outlines must not
    # become yellow merely because it is close in RGB distance.
    neutral = np.ptp(rgb, axis=2) < 40
    labels[neutral] = np.where(rgb.mean(axis=2)[neutral] >= 145, 1, 0)
    silhouette_pixels = pixel_region(opaque)
    x0, y0, x1, y1 = silhouette_pixels.bounds
    left, top, right, bottom = target_bounds
    scale = min((right - left) / (x1 - x0), (bottom - top) / (y1 - y0))

    def position(shape):
        shape = affinity.translate(shape, -(x0 + x1) / 2, -y0)
        shape = affinity.scale(shape, xfact=scale, yfact=scale, origin=(0, 0))
        return affinity.translate(shape, (left + right) / 2, top)

    # 0.025 mm is less than half a source pixel at this logo size; it removes
    # pixel stairs while retaining the source's pointed tail and letter corners.
    silhouette = position(silhouette_pixels).simplify(.025, preserve_topology=True)
    regions = {}
    raw_regions = {}
    for label, key in [(1, '7'), (3, '9'), (2, '8')]:
        raw = position(pixel_region(opaque & (labels == label)))
        raw_regions[key] = raw
        shape = raw.simplify(.025, preserve_topology=True).intersection(silhouette)
        shape = shape.difference(unary_union(list(regions.values())))
        regions[key] = unary_union([p for p in polygons(shape) if p.area >= .008])
    regions['6'] = silhouette.difference(unary_union(list(regions.values())))
    # Compare reconstructed non-black colour regions with the input bitmap.
    overlaps = {key: round(shape.intersection(raw_regions[key]).area /
                          shape.union(raw_regions[key]).area, 5)
                for key, shape in regions.items() if key != '6'}
    assert min(overlaps.values()) > .98, overlaps
    assert abs(unary_union(list(regions.values())).area - silhouette.area) < 1e-7
    return regions, overlaps, scale


def main():
    with zipfile.ZipFile(OUT / 'EIE_SOPHIA_43_v4_PLA.3mf') as archive:
        baseline = ET.fromstring(archive.read('3D/Objects/object_1.model'))
    old_objects = {o.get('id'): mesh(o) for o in baseline.findall('.//' + T('object'))}
    old_logo = unary_union([footprint(*old_objects[k]) for k in PALETTE])
    regions, overlaps, scale = trace_artwork(old_logo.bounds)
    svg = ['<svg xmlns="http://www.w3.org/2000/svg" viewBox="-16 -43 32 34">']
    for key in ('6', '8', '9', '7'):
        for poly in polygons(regions[key]):
            rings = [poly.exterior] + list(poly.interiors)
            d = ' '.join('M ' + ' L '.join(f'{x:.5f},{y:.5f}' for x, y in r.coords) + ' Z' for r in rings)
            svg.append(f'<path fill="{PALETTE[key]}" fill-rule="evenodd" d="{d}"/>')
    svg.append('</svg>')
    (ROOT / 'logo/EIE_Logo_v5.svg').write_text('\n'.join(svg), encoding='utf-8')
    previews, artifacts, reports = [], [], []
    for who in ('SOPHIA_43', 'JASON_4'):
        with zipfile.ZipFile(OUT / f'EIE_{who}_v4_PLA.3mf') as archive:
            files = {key: archive.read(key) for key in archive.namelist()}
        model = ET.fromstring(files['3D/Objects/object_1.model'])
        main_model = ET.fromstring(files['3D/3dmodel.model'])
        settings = ET.fromstring(files['Metadata/model_settings.config'])
        before = {o.get('id'): mesh(o) for o in model.findall('.//' + T('object'))}
        for key in PALETTE:
            base, top = before[key][0][:, 1].min(), before[key][0][:, 1].max()
            vertices, triangles = extrude(regions[key], base=base, top=top)
            setmesh(model, key, vertices, triangles)
            settings.find(f".//part[@id='{key}']/mesh_stat").set('face_count', str(len(triangles)))
        settings.find('object/metadata[@face_count]').set('face_count', str(len(model.findall('.//' + T('triangle')))))
        after = {o.get('id'): mesh(o) for o in model.findall('.//' + T('object'))}
        for key in ('1', '2', '3', '5', '10', '11'):
            assert np.array_equal(before[key][0], after[key][0]), key
            assert np.array_equal(before[key][1], after[key][1]), key
        for axis in (np.min, np.max):
            assert np.allclose(axis(np.concatenate([v for v, _ in before.values()]), axis=0),
                               axis(np.concatenate([v for v, _ in after.values()]), axis=0))
        shapes = {k: footprint(*data) for k, data in after.items()}
        logo = unary_union([shapes[k] for k in PALETTE])
        name = shapes['2'].union(shapes['10'])
        assert logo.difference(shapes['1']).area < 1e-8
        assert logo.intersection(shapes['5']).area < 1e-8
        assert logo.distance(name) > 5
        for a in PALETTE:
            for b in PALETTE:
                if a != b:
                    assert shapes[a].intersection(shapes[b]).area < 1e-8
        stem = f'EIE_{who}_v5_PLA'
        preview = OUT / f'{stem}_Vorschau.png'
        im, png = render(model, main_model, preview)
        previews.append(im)
        for key in files:
            if key.endswith('.png'):
                files[key] = png
        for key, tree in [('3D/Objects/object_1.model', model), ('Metadata/model_settings.config', settings)]:
            files[key] = ET.tostring(tree, encoding='utf-8', xml_declaration=True)
        project = OUT / f'{stem}.3mf'
        with zipfile.ZipFile(project, 'w', zipfile.ZIP_DEFLATED) as archive:
            for key, data in files.items():
                archive.writestr(key, data)
        artifacts.extend([project, preview])
        reports.append({'tag': who, 'logo_width_mm': round(logo.bounds[2] - logo.bounds[0], 3),
                        'logo_height_mm': round(logo.bounds[3] - logo.bounds[1], 3),
                        'logo_name_gap_mm': round(logo.distance(name), 3),
                        'source_pixel_mm': round(scale, 5), 'colour_region_iou': overlaps})
    comparison = Image.new('RGB', (1500, 1300), '#e9edf0')
    for i, im in enumerate(previews):
        comparison.paste(im, (750 * i, 0))
    preview = OUT / 'SOPHIA_43_JASON_4_v5_PLA_Vorschau.png'
    comparison.save(preview)
    artifacts.append(preview)
    readme = OUT / 'Anleitung_SOPHIA_JASON_v5_PLA.txt'
    readme.write_text('''EIE HOCKEY BAG TAGS – VERSION 5 – PLA

Das Puck-Logo wurde aus der neuen transparenten PNG-Grafik neu aufgebaut.
Die Fotoperspektive und die unruhigen Fotokonturen sind damit ersetzt.
Das Seitenverhältnis der neuen Vorlage bleibt erhalten; Höhe, obere Position
und horizontale Zentrierung entsprechen der freigegebenen Version 4.
Name, Nummer, gelbe Konturen, Befestigungsschlitz und Grundform sind unverändert.
Abmessungen: 55,88 × 106,68 mm; maximale Gesamtdicke 3,96 mm.

Die Schriftzug-Grafik EIE HOCKEY ist als Referenz im Projekt hinterlegt;
auf den Tags bleibt das bisher gewählte Puck-Logo.
Beide Grafiken verwenden leicht unterschiedliche Grün- und Gelbtöne.
Für den Druck bleiben es vier Filamente: Weiss, Grün, Gelb und Schwarz.
Gewähltes Grün: ColorFabb PLA High Speed Pro Moss Green (RAL 6005).
Bildschirmfarben sind eine Vorschau, keine Messung des gedruckten Filaments.

3MF in Bambu Studio als Projekt öffnen, Filamente zuordnen und neu slicen.
Die feinen Logo-Spitzen in der Schichtvorschau prüfen; sehr feine Details
können bei einer 0,4-mm-Düse vereinfacht werden.
Profil: Bambu Lab A1 / 0,4 mm / Generic PLA. Druckparameter gegenüber v4 unverändert.
Geometrie und Farbübergänge geprüft; kein Probedruck durchgeführt.

Schriften: College und College Bold, Matthew Welch; Lizenz beigefügt.
Lizenzmetadaten der ursprünglichen 3MF bleiben erhalten.
''', encoding='utf-8')
    artifacts += [readme, ROOT / 'fonts/college/license.txt']
    with zipfile.ZipFile(OUT / 'EIE_SOPHIA_43_JASON_4_v5_PLA_Paket.zip', 'w', zipfile.ZIP_DEFLATED) as archive:
        for path in artifacts:
            archive.write(path, path.name)
    shutil.copyfile(OUT / 'EIE_SOPHIA_43_v5_PLA.3mf', ROOT / 'tag_generator/assets/template.3mf')
    (OUT / 'Pruefung_v5_PLA.json').write_text(json.dumps(reports, indent=2), encoding='utf-8')
    print(json.dumps(reports, indent=2))


if __name__ == '__main__':
    main()
