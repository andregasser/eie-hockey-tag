"""Executed by Blender in a fresh background process, never by the web server."""
import json
from pathlib import Path
import sys

import bpy

request_path, result_path = sys.argv[sys.argv.index('--') + 1:]
request = json.loads(Path(request_path).read_text(encoding='utf-8'))
result = {}
for key in ('name', 'number'):
    bpy.ops.object.select_all(action='DESELECT')
    curve = bpy.data.curves.new(key, 'FONT')
    curve.body = request[key]
    curve.font = bpy.data.fonts.load(request[key + '_font'])
    curve.size = 1
    curve.extrude = .1
    curve.resolution_u = 8
    obj = bpy.data.objects.new(key, curve)
    bpy.context.collection.objects.link(obj)
    bpy.context.view_layer.objects.active = obj
    obj.select_set(True)
    bpy.ops.object.convert(target='MESH')
    mesh = obj.data
    mesh.calc_loop_triangles()
    result[key] = {'v': [list(v.co) for v in mesh.vertices],
                   't': [list(t.vertices) for t in mesh.loop_triangles]}
Path(result_path).write_text(json.dumps(result), encoding='utf-8')
