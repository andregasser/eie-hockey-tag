"""Run with python -m unittest discover -s tests -v (Blender required)."""
from pathlib import Path
import collections
import http.client
import json
import tempfile
import threading
import unittest
import zipfile
import xml.etree.ElementTree as ET

import numpy as np

from tag_generator.engine import ROOT, TEMPLATE, InputError, build_tag, normalize
from tag_generator.geometry import T, footprint, mesh
from tag_generator.server import GeneratorServer


def read_project(path):
    with zipfile.ZipFile(path) as archive:
        model = ET.fromstring(archive.read('3D/Objects/object_1.model'))
        files = {key: archive.read(key) for key in archive.namelist()}
    objects = {obj.get('id'): mesh(obj) for obj in model.findall('.//' + T('object'))}
    return objects, files


class InputTests(unittest.TestCase):
    def test_normalization_and_leading_zero(self):
        self.assertEqual(normalize('  müller   meier ', ' 04 '), ('MUELLER MEIER', '04'))
        self.assertEqual(normalize("O'NEILL", '0'), ("O'NEILL", '0'))

    def test_invalid_input_is_rejected(self):
        for name, number in [('', '4'), ('  ', '4'), ('A' * 25, '4'), ('<script>', '4'),
                             ('JASON', '-1'), ('JASON', '100'), ('JASON', '٤'), ('JASON', 4),
                             ('..', '4'), ('A/B', '4'), (None, '4')]:
            with self.subTest(name=name, number=number), self.assertRaises(InputError):
                normalize(name, number)


class GeometryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory()
        cls.results = {}
        for name, number in [('SOPHIA', '43'), ('JASON', '4'), ('MAX', '88'),
                             ('ALEXANDER-MAXIMILIAN', '00'), ('MUELLER', '07')]:
            cls.results[name] = build_tag(name, number, Path(cls.temp.name) / name)

    @classmethod
    def tearDownClass(cls):
        cls.temp.cleanup()

    def test_approved_v4_geometry_is_reproduced(self):
        for name, number in [('SOPHIA', '43'), ('JASON', '4')]:
            new, _ = read_project(self.results[name]['project'])
            approved, _ = read_project(ROOT / f'output/EIE_{name}_{number}_v4_PLA.3mf')
            for key in ('2', '3', '10', '11'):
                with self.subTest(name=name, part=key):
                    actual = footprint(*new[key])
                    expected = footprint(*approved[key])
                    self.assertLess(actual.symmetric_difference(expected).area, 1e-6)
                    self.assertLess(actual.hausdorff_distance(expected), 1e-6)

    def test_static_geometry_profiles_and_dimensions_are_preserved(self):
        original, original_files = read_project(TEMPLATE)
        original_vertices = np.concatenate([v for v, _ in original.values()])
        for result in self.results.values():
            actual, files = read_project(result['project'])
            for key in ('1', '5', '6', '7', '8', '9'):
                np.testing.assert_array_equal(actual[key][0], original[key][0])
                np.testing.assert_array_equal(actual[key][1], original[key][1])
            np.testing.assert_allclose(np.concatenate([v for v, _ in actual.values()]).min(axis=0), original_vertices.min(axis=0))
            np.testing.assert_allclose(np.concatenate([v for v, _ in actual.values()]).max(axis=0), original_vertices.max(axis=0))
            self.assertEqual(files['Metadata/project_settings.config'], original_files['Metadata/project_settings.config'])
            main = ET.fromstring(files['3D/3dmodel.model'])
            baseline = ET.fromstring(original_files['3D/3dmodel.model'])
            self.assertEqual(main.find('.//' + T('item')).attrib, baseline.find('.//' + T('item')).attrib)
            self.assertEqual(main.find(T('metadata') + "[@name='License']").text,
                             baseline.find(T('metadata') + "[@name='License']").text)
            self.assertEqual(main.find(T('metadata') + "[@name='Title']").text,
                             f"EIE {result['report']['name']} {result['report']['number']}")

    def test_generated_text_is_closed_with_positive_volume(self):
        for result in self.results.values():
            objects, files = read_project(result['project'])
            settings = ET.fromstring(files['Metadata/model_settings.config'])
            for key in ('2', '3', '10', '11'):
                vertices, triangles = objects[key]
                edges = collections.Counter(tuple(sorted((a, b))) for tri in triangles
                                            for a, b in zip(tri, np.roll(tri, -1)))
                self.assertTrue(all(count == 2 for count in edges.values()))
                volume = np.einsum('ij,ij->i', vertices[triangles[:, 0]],
                                  np.cross(vertices[triangles[:, 1]], vertices[triangles[:, 2]])).sum() / 6
                self.assertGreater(volume, 0)
                self.assertEqual(int(settings.find(f".//part[@id='{key}']/mesh_stat").get('face_count')), len(triangles))
            self.assertGreaterEqual(result['report']['logo_to_name_mm'], 5)
            self.assertGreaterEqual(result['report']['name_to_number_mm'], 3)
            self.assertGreaterEqual(result['report']['number_to_frame_mm'], 3)

    def test_digit_holes_and_independent_colours(self):
        for name, expected_holes in [('SOPHIA', 1), ('JASON', 1), ('MAX', 4),
                                     ('ALEXANDER-MAXIMILIAN', 2), ('MUELLER', 1)]:
            objects, _ = read_project(self.results[name]['project'])
            white, yellow = footprint(*objects['3']), footprint(*objects['11'])
            polys = [white] if white.geom_type == 'Polygon' else list(white.geoms)
            self.assertEqual(sum(len(p.interiors) for p in polys), expected_holes)
            self.assertLess(white.intersection(yellow).area, 1e-7)
        self.assertLess(self.results['ALEXANDER-MAXIMILIAN']['report']['name_height_mm'],
                        self.results['SOPHIA']['report']['name_height_mm'])


class ServerTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.server = GeneratorServer(0, self.temp.name)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join()
        self.temp.cleanup()

    def request(self, method, path, payload=None, headers=None):
        conn = http.client.HTTPConnection('127.0.0.1', self.server.server_port, timeout=120)
        conn.request(method, path, json.dumps(payload) if payload is not None else None, headers or {})
        response = conn.getresponse()
        status, data = response.status, response.read()
        conn.close()
        return status, data

    def test_page_and_rejection_paths(self):
        status, data = self.request('GET', '/')
        self.assertEqual(status, 200)
        self.assertIn(b'Name', data)
        self.assertEqual(self.request('GET', '/', headers={'Host': 'example.com'})[0], 403)
        self.assertEqual(self.request('POST', '/api/generate', {'name': 'MAX', 'number': '8'})[0], 403)
        headers = {'X-Tag-Generator': '1', 'Origin': 'https://example.com'}
        self.assertEqual(self.request('POST', '/api/generate', {}, headers)[0], 403)
        self.assertEqual(self.request('POST', '/api/generate', {}, {'X-Tag-Generator': '1'})[0], 400)
        self.assertEqual(self.request('GET', '/files/../../fonts/college/license.txt')[0], 404)

    def test_generate_preview_and_download(self):
        status, data = self.request('POST', '/api/generate', {'name': 'Test', 'number': '04'},
                                    {'X-Tag-Generator': '1', 'Origin': self.server.origin})
        self.assertEqual(status, 200, data)
        result = json.loads(data)
        self.assertEqual(result['report']['name'], 'TEST')
        self.assertEqual(result['report']['number'], '04')
        status, png = self.request('GET', result['preview'])
        self.assertEqual(status, 200)
        self.assertTrue(png.startswith(b'\x89PNG\r\n'))
        status, project = self.request('GET', result['project'])
        self.assertEqual(status, 200)
        self.assertTrue(project.startswith(b'PK'))


if __name__ == '__main__':
    unittest.main()
