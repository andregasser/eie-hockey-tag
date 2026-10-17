from pathlib import Path
import zipfile,xml.etree.ElementTree as E,json,math,collections
from PIL import Image,ImageDraw
ROOT=Path(__file__).parent
SRC=Path('/home/andre/.codex/attachments/41d8d321-cd6d-4b89-915d-93550cb11093/Hockey_Bag_Tag.3mf')
NS='http://schemas.microsoft.com/3dmanufacturing/core/2015/02';P='http://schemas.microsoft.com/3dmanufacturing/production/2015/06'
E.register_namespace('',NS);E.register_namespace('p',P);E.register_namespace('BambuStudio','http://schemas.bambulab.com/package/2021')
def tag(s):return '{'+NS+'}'+s
z=zipfile.ZipFile(SRC);files={n:z.read(n) for n in z.namelist()};model=E.fromstring(files['3D/Objects/object_1.model']);settings=E.fromstring(files['Metadata/model_settings.config']);main=E.fromstring(files['3D/3dmodel.model']);texts=json.load(open('/tmp/text-mesh.json'))
meshes={}
def readmesh(o):return [[float(v.get(a)) for a in ('x','y','z')] for v in o.findall('.//'+tag('vertex'))],[[int(t.get(a)) for a in ('v1','v2','v3')] for t in o.findall('.//'+tag('triangle'))]
def putmesh(o,vs,ts):
 old=o.find(tag('mesh'))
 if old is not None:o.remove(old)
 mesh=E.SubElement(o,tag('mesh'));vroot=E.SubElement(mesh,tag('vertices'));troot=E.SubElement(mesh,tag('triangles'))
 for v in vs:E.SubElement(vroot,tag('vertex'),{a:format(n,'.10g') for a,n in zip(('x','y','z'),v)})
 for t in ts:E.SubElement(troot,tag('triangle'),{a:str(n) for a,n in zip(('v1','v2','v3'),t)})
 meshes[o.get('id')]=(vs,ts)
for o in model.findall('.//'+tag('object')):
 key=o.get('id');vs,ts=readmesh(o)
 if key=='1':
  # The painted rink is a partitioned surface. Flatten its relief and weld the surface.
  index={};new=[];mapping=[]
  for x,y,zz in vs:
   q=(round(x,7),round(3.4289999 if y>2.9 else y,7),round(zz,7))
   if q not in index:index[q]=len(new);new.append(q)
   mapping.append(index[q])
  tris=[]
  for t in ts:
   t=[mapping[i] for i in t]
   if len(set(t))<3:continue
   a,b,c=[new[i] for i in t];u=[b[i]-a[i] for i in range(3)];v=[c[i]-a[i] for i in range(3)];cross=[u[1]*v[2]-u[2]*v[1],u[2]*v[0]-u[0]*v[2],u[0]*v[1]-u[1]*v[0]]
   if sum(x*x for x in cross)>1e-20:tris.append(t)
  vs,ts=new,tris
 else:
  bounds=[(min(v[i] for v in vs),max(v[i] for v in vs)) for i in range(3)];vs=texts[key]['v'];ts=texts[key]['t'];b=[(min(v[i] for v in vs),max(v[i] for v in vs)) for i in range(3)]
  vs=[[bounds[i][0]+(v[i]-b[i][0])/(b[i][1]-b[i][0])*(bounds[i][1]-bounds[i][0]) for i in range(3)] for v in vs]
 putmesh(o,vs,ts)
# Closed yellow band on the front; inset from the original perimeter.
def loop(inset):
 hx=44.4500008-inset;hz=25.3999996-inset;r=6.35-inset;pts=[]
 for cx,cz,start in [(hx-r,hz-r,0),(-hx+r,hz-r,90),(-hx+r,-hz+r,180),(hx-r,-hz+r,270)]:
  for i in range(17):
   a=math.radians(start+i*90/16);pts.append((cx+r*math.cos(a),cz+r*math.sin(a)))
 return pts
outer=loop(1.3);inner=loop(2.5);n=len(outer);vs=[]
for y in [3.4289999,3.8289999]:
 for lp in [outer,inner]:vs.extend((x,y,zz) for x,zz in lp)
ts=[]
for i in range(n):
 j=(i+1)%n
 # Quad orientations checked against outward normals below.
 for a,b,c,d in [(i,j,n+j,n+i),(2*n+i,3*n+i,3*n+j,2*n+j),(i,2*n+i,2*n+j,j),(n+i,n+j,3*n+j,3*n+i)]:ts.extend([(a,b,c),(a,c,d)])
# Ensure positive signed volume.
vol=sum(sum(vs[a][k]*(vs[b][(k+1)%3]*vs[c][(k+2)%3]-vs[b][(k+2)%3]*vs[c][(k+1)%3]) for k in range(3)) for a,b,c in ts)/6
if vol<0:ts=[(a,c,b) for a,b,c in ts]
o=E.SubElement(model.find(tag('resources')),tag('object'),{'id':'5','type':'model'});putmesh(o,vs,ts)
comps=main.find('.//'+tag('components'));E.SubElement(comps,tag('component'),{'{'+P+'}path':'/3D/Objects/object_1.model','objectid':'5','transform':'1 0 0 0 1 0 0 0 1 0 0 0'})
obj=settings.find('object');obj.find("metadata[@key='name']").set('value','EIE Hockey Bag Tag')
for part in obj.findall('part'):
 key=part.get('id');ex=part.find("metadata[@key='extruder']")
 if ex is None:ex=E.SubElement(part,'metadata',{'key':'extruder'})
 ex.set('value','2' if key=='1' else '1');part.find('mesh_stat').set('face_count',str(len(meshes[key][1])))
 ti=part.find('text_info')
 if ti is not None:ti.set('font_name','Graduate');ti.set('font_version','1.001');ti.set('style_name','Regular');ti.set('bold','0')
part=E.SubElement(obj,'part',{'id':'5','subtype':'normal_part'});E.SubElement(part,'metadata',{'key':'name','value':'Gelber Rahmen'});E.SubElement(part,'metadata',{'key':'extruder','value':'3'});E.SubElement(part,'mesh_stat',{'face_count':str(len(ts))})
obj.find('metadata[@face_count]').set('face_count',str(sum(len(t) for v,t in meshes.values())))
cfg=json.loads(files['Metadata/project_settings.config']);cfg['filament_colour']=['#FFFFFF','#123E2B','#F4BE19','#123E2B'];cfg['filament_multi_colour']=cfg['filament_colour']
files['Metadata/project_settings.config']=json.dumps(cfg,indent=4).encode()
for name,r in [('3D/3dmodel.model',main),('3D/Objects/object_1.model',model),('Metadata/model_settings.config',settings)]:files[name]=E.tostring(r,encoding='utf-8',xml_declaration=True)
# Front-view preview of the actual triangles, with original component transforms.
im=Image.new('RGB',(750,1300),'#e9edf0');draw=ImageDraw.Draw(im);faces=[]
for comp in comps:
 key=comp.get('objectid');v,t=meshes[key];m=list(map(float,comp.get('transform').split()));vv=[[sum(q[k]*m[k*3+j] for k in range(3))+m[9+j] for j in range(3)] for q in v]
 for tri in t:
  points=[vv[i] for i in tri];faces.append((sum(q[1] for q in points),[(375-q[2]*1.1*10.5,650+q[0]*1.2*10.5) for q in points],{'1':'#123E2B','2':'#FFFFFF','3':'#FFFFFF','5':'#F4BE19'}[key]))
for _,pts,color in sorted(faces,key=lambda f:f[0]):draw.polygon(pts,fill=color)
im.save(ROOT/'output/EIE_Hockey_Tag_Vorschau.png')
# Replace outdated slicer previews so the archive does not show the old design.
import io
buf=io.BytesIO();im.save(buf,format='PNG')
for name in files:
 if name.endswith('.png'):files[name]=buf.getvalue()
with zipfile.ZipFile(ROOT/'output/EIE_Hockey_Tag.3mf','w',zipfile.ZIP_DEFLATED) as out:
 for name,data in files.items():out.writestr(name,data)
# Mesh topology audit (coordinate-welded edges).
for key,(vs,ts) in meshes.items():
 weld={};ids=[]
 for v in vs:
  q=tuple(round(x,6) for x in v)
  if q not in weld:weld[q]=len(weld)
  ids.append(weld[q])
 edges=collections.Counter(tuple(sorted((ids[a],ids[b]))) for t in ts for a,b in zip(t,(t[1],t[2],t[0])))
 print('part',key,'triangles',len(ts),'nonmanifold_edges',sum(n!=2 for n in edges.values()))
