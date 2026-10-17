"""Regenerate the four lettering parts; keep the approved tag and PLA profile."""
from datetime import date
from pathlib import Path
import json
import os
import re
import shutil
import subprocess
import tempfile
import unicodedata
import zipfile
import xml.etree.ElementTree as ET

import numpy as np
from shapely import affinity
from shapely.geometry import Polygon
from shapely.ops import unary_union

from .geometry import T, NS, extrude, footprint, mesh, render, setmesh

ROOT = Path(__file__).resolve().parent.parent
TEMPLATE = Path(__file__).parent / 'assets' / 'template.3mf'
ET.register_namespace('', NS)
ET.register_namespace('p', 'http://schemas.microsoft.com/3dmanufacturing/production/2015/06')


class InputError(ValueError):
    """A message that can be shown directly to the user."""


def normalize(name, number):
    if not isinstance(name, str) or not isinstance(number, str):
        raise InputError('Bitte Name und Nummer als Text eingeben.')
    name = ' '.join(unicodedata.normalize('NFC', name).upper().split())
    name = name.replace('Ä', 'AE').replace('Ö', 'OE').replace('Ü', 'UE')
    if not re.fullmatch(r"[A-Z][A-Z .'-]{0,23}", name):
        raise InputError('Bitte 1–24 Zeichen eingeben: A–Z, Leerzeichen, Bindestrich, Punkt oder Apostroph. Umlaute werden zu AE, OE und UE.')
    number = number.strip()
    if not re.fullmatch(r'[0-9]{1,2}', number):
        raise InputError('Bitte eine ein- oder zweistellige Nummer eingeben (0–99, auch 04).')
    return name, number


def blender_path():
    configured = os.environ.get('BLENDER_PATH')
    candidates = [configured] if configured else [shutil.which('blender'),
        '/Applications/Blender.app/Contents/MacOS/Blender']
    if os.name == 'nt' and not configured:
        candidates += [str(p) for p in sorted(
            Path(os.environ.get('PROGRAMFILES', 'C:/Program Files')).glob('Blender Foundation/Blender */blender.exe'), reverse=True)]
    for candidate in candidates:
        if candidate and Path(candidate).is_file():
            return str(Path(candidate).resolve())
    raise InputError('Blender wurde nicht gefunden. Bitte Blender installieren oder BLENDER_PATH auf die Blender-Programmdatei setzen; siehe README.')


def text_meshes(name, number):
    with tempfile.TemporaryDirectory(prefix='eie-text-') as directory:
        request, result = Path(directory) / 'request.json', Path(directory) / 'result.json'
        request.write_text(json.dumps({
            'name': name, 'number': number,
            'name_font': str(ROOT / 'fonts/college/collegeb.ttf'),
            'number_font': str(ROOT / 'fonts/college/college.ttf'),
        }), encoding='utf-8')
        try:
            process = subprocess.run([
                blender_path(), '--background', '--factory-startup', '--threads', '1',
                '--python-exit-code', '1', '--python', str(Path(__file__).with_name('blender_text.py')),
                '--', str(request), str(result),
            ], capture_output=True, text=True, timeout=90)
        except subprocess.TimeoutExpired as exc:
            raise InputError('Die Schrifterzeugung hat zu lange gedauert. Bitte erneut versuchen.') from exc
        if process.returncode or not result.exists():
            raise RuntimeError('Blender konnte die Schrift nicht erzeugen. ' + process.stderr[-1000:])
        return json.loads(result.read_text(encoding='utf-8'))


def lettering(data, height, width, centre):
    vertices = np.asarray(data['v'])
    cap = vertices[:, 2].max()
    polygons = []
    for triangle in data['t']:
        points = vertices[triangle]
        if np.max(np.abs(points[:, 2] - cap)) < 1e-7:
            poly = Polygon(points[:, :2])
            if poly.area > 1e-12:
                polygons.append(poly)
    shape = unary_union(polygons).simplify(1e-7)
    if shape.is_empty or not shape.is_valid:
        raise InputError('Diese Beschriftung konnte nicht erzeugt werden.')
    left, top, right, bottom = shape.bounds
    scale = min(height / (bottom - top), width / (right - left))
    shape = affinity.translate(shape, -(left + right) / 2, -(top + bottom) / 2)
    shape = affinity.scale(shape, xfact=scale, yfact=-scale, origin=(0, 0))
    return affinity.translate(shape, yoff=centre)


def build_tag(name, number, destination):
    """Write a checked 3MF, a mesh-rendered PNG and a report into destination."""
    name, number = normalize(name, number)
    text = text_meshes(name, number)
    with zipfile.ZipFile(TEMPLATE) as archive:
        files = {key: archive.read(key) for key in archive.namelist()}
    model = ET.fromstring(files['3D/Objects/object_1.model'])
    main = ET.fromstring(files['3D/3dmodel.model'])
    settings = ET.fromstring(files['Metadata/model_settings.config'])
    title = f'EIE {name} {number}'
    settings.find("object/metadata[@key='name']").set('value', title)
    for metadata in main.findall(T('metadata')):
        if metadata.get('name') == 'Title':
            metadata.text = title
        elif metadata.get('name') == 'ModificationDate':
            metadata.text = date.today().isoformat()

    # These are the exact operations used for the approved v4 lettering.
    white_name = lettering(text['name'], 11, 44.4, .2)
    white_number = lettering(text['number'], 30, 40, 27)
    white_number = white_number.buffer(.45, join_style=2).buffer(-.0001, join_style=2).buffer(.35, join_style=2)
    shapes = {'2': white_name, '10': white_name.buffer(.5, join_style=2).difference(white_name),
              '3': white_number, '11': white_number.buffer(.6, join_style=2).difference(white_number)}
    for key, shape in shapes.items():
        vertices, triangles = extrude(shape)
        setmesh(model, key, vertices, triangles)
        part = settings.find(f"object/part[@id='{key}']")
        label = f'Name {name}' if key in ('2', '10') else f'Nummer {number}'
        label += ' – Weiss' if key in ('2', '3') else ' – Gelbe Kontur'
        part.find("metadata[@key='name']").set('value', label)
        part.find('mesh_stat').set('face_count', str(len(triangles)))
    settings.find('object/metadata[@face_count]').set('face_count', str(len(model.findall('.//' + T('triangle')))))

    parts = {obj.get('id'): footprint(*mesh(obj)) for obj in model.findall('.//' + T('object'))}
    logo = unary_union([parts[k] for k in ('6', '7', '8', '9')])
    name_shape = parts['2'].union(parts['10'])
    number_shape = parts['3'].union(parts['11'])
    decoration = unary_union([logo, name_shape, number_shape])
    report = {'name': name, 'number': number,
              'logo_to_name_mm': round(logo.distance(name_shape), 3),
              'name_to_number_mm': round(name_shape.distance(number_shape), 3),
              'number_to_frame_mm': round(number_shape.distance(parts['5']), 3),
              'name_height_mm': round(parts['2'].bounds[3] - parts['2'].bounds[1], 3),
              'width_mm': 55.88, 'height_mm': 106.68, 'max_thickness_mm': 3.96}
    if (decoration.difference(parts['1']).area > 1e-7
            or decoration.intersection(parts['5']).area > 1e-7
            or report['logo_to_name_mm'] < 5
            or report['name_to_number_mm'] < 3
            or report['number_to_frame_mm'] < 3):
        raise InputError('Die Beschriftung passt nicht mit genügend Abstand auf den Tag. Bitte einen kürzeren Namen wählen.')
    # Very short names reach 11 mm; longer names are scaled down uniformly.
    report['small_name'] = report['name_height_mm'] < 6
    destination = Path(destination)
    destination.mkdir(parents=True, exist_ok=True)
    stem = 'EIE_' + re.sub(r'[^A-Z0-9]+', '_', name).strip('_') + '_' + number + '_PLA'
    preview = destination / (stem + '.png')
    _, png = render(model, main, preview)
    for key in files:
        if key.endswith('.png'):
            files[key] = png
    for key, tree in [('3D/Objects/object_1.model', model), ('3D/3dmodel.model', main),
                      ('Metadata/model_settings.config', settings)]:
        files[key] = ET.tostring(tree, encoding='utf-8', xml_declaration=True)
    project = destination / (stem + '.3mf')
    with zipfile.ZipFile(project, 'w', zipfile.ZIP_DEFLATED) as archive:
        for key, data in files.items():
            archive.writestr(key, data)
    with zipfile.ZipFile(project) as archive:
        if archive.testzip() is not None:
            raise RuntimeError('Die 3MF-Datei konnte nicht vollständig geschrieben werden.')
    (destination / (stem + '.json')).write_text(json.dumps(report, indent=2), encoding='utf-8')
    return {'project': project, 'preview': preview, 'report': report}
