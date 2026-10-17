import bpy,json
font=bpy.data.fonts.load('/home/andre/projects/eie-hockey-tag/fonts/college/collegeb.ttf')
out={}
for key,body in [('2','NAME'),('3','00')]:
 c=bpy.data.curves.new('Text','FONT');c.body=body;c.font=font;c.size=1;c.extrude=.1;c.resolution_u=8
 ob=bpy.data.objects.new('Text',c);bpy.context.collection.objects.link(ob);bpy.context.view_layer.objects.active=ob;ob.select_set(True)
 bpy.ops.object.convert(target='MESH');m=ob.data;m.calc_loop_triangles()
 out[key]={'v':[list(v.co) for v in m.vertices],'t':[list(t.vertices) for t in m.loop_triangles]};ob.select_set(False)
json.dump(out,open('/home/andre/projects/eie-hockey-tag/typography/text-mesh.json','w'))
