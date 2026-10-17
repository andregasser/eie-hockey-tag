from pathlib import Path
import json,zipfile,xml.etree.ElementTree as E,collections,io,math
import numpy as np,mapbox_earcut as earcut
from shapely.geometry import Polygon
from shapely.geometry.polygon import orient
from PIL import Image,ImageDraw
ROOT=Path(__file__).resolve().parent.parent;OUT=ROOT/'output'
NS='http://schemas.microsoft.com/3dmanufacturing/core/2015/02';P='http://schemas.microsoft.com/3dmanufacturing/production/2015/06'
E.register_namespace('',NS);E.register_namespace('p',P)
T=lambda n:'{'+NS+'}'+n
with zipfile.ZipFile(OUT/'EIE_Hockey_Tag.3mf') as z:files={n:z.read(n) for n in z.namelist()}
model=E.fromstring(files['3D/Objects/object_1.model']);main=E.fromstring(files['3D/3dmodel.model']);settings=E.fromstring(files['Metadata/model_settings.config']);comps=main.find('.//'+T('components'));obj=settings.find('object')
vectors=json.loads((ROOT/'logo/logo_vectors.json').read_text())
def clean(ring):
 pts=list(ring.coords)[:-1]
 while True:
  new=[]
  for i,b in enumerate(pts):
   a=pts[i-1];c=pts[(i+1)%len(pts)]
   cross=(b[0]-a[0])*(c[1]-b[1])-(b[1]-a[1])*(c[0]-b[0])
   if abs(cross)>1e-10:new.append(b)
  if len(new)==len(pts):return new
  if len(new)<3:raise ValueError('Degenerate ring')
  pts=new

def extrude(parts):
 vs=[];ts=[]
 polygons=[]
 for data in parts:
  # Resolve point-touching boundaries with a 0.001 mm clearance, below print resolution.
  p=Polygon(data['outer'],data['holes']).buffer(-.001,join_style=2)
  polygons.extend([p] if p.geom_type=='Polygon' else list(p.geoms))
 for p in polygons:
  p=orient(p,sign=1)
  if p.area<1e-9:continue
  rings=[clean(p.exterior)]+[clean(r) for r in p.interiors]
  coords=np.array([p for ring in rings for p in ring]);ends=np.cumsum([len(r) for r in rings],dtype=np.uint32)
  faces=earcut.triangulate_float64(coords,ends).reshape(-1,3);n=len(coords);start=len(vs)
  for h in [3.4289999,4.2289999]:
   for u,v in coords:vs.append(((v-42.0)/1.2,h,-(u-vectors['width']/2)/1.1))
  local=[]
  for a,b,c in faces:
   u=coords[b]-coords[a];v=coords[c]-coords[a]
   if u[0]*v[1]-u[1]*v[0]<0:b,c=c,b
   local.extend([(int(a),int(c),int(b)),(int(a+n),int(b+n),int(c+n))])
  offset=0
  for ring in rings:
   for i in range(len(ring)):
    a=offset+i;b=offset+(i+1)%len(ring);local.extend([(a,b,b+n),(a,b+n,a+n)])
   offset+=len(ring)
  # Mapping from (u,v,height) to model space reverses handedness.
  ts.extend((start+a,start+c,start+b) for a,b,c in local)
 return vs,ts
for color,key,label,filament in [('0','6','Logo Schwarz','4'),('1','7','Logo Weiss','1'),('2','8','Logo Gruen','2'),('3','9','Logo Gelb','3')]:
 vs,ts=extrude(vectors['regions'][color]);o=E.SubElement(model.find(T('resources')),T('object'),{'id':key,'type':'model'});mesh=E.SubElement(o,T('mesh'));vr=E.SubElement(mesh,T('vertices'));tr=E.SubElement(mesh,T('triangles'))
 for v in vs:E.SubElement(vr,T('vertex'),{a:format(float(n),'.10g') for a,n in zip(('x','y','z'),v)})
 for t in ts:E.SubElement(tr,T('triangle'),{a:str(n) for a,n in zip(('v1','v2','v3'),t)})
 E.SubElement(comps,T('component'),{'{'+P+'}path':'/3D/Objects/object_1.model','objectid':key,'transform':'1 0 0 0 1 0 0 0 1 0 0 0'})
 part=E.SubElement(obj,'part',{'id':key,'subtype':'normal_part'});E.SubElement(part,'metadata',{'key':'name','value':label});E.SubElement(part,'metadata',{'key':'extruder','value':filament});E.SubElement(part,'mesh_stat',{'face_count':str(len(ts))})
 edges=collections.Counter(tuple(sorted((a,b))) for t in ts for a,b in zip(t,(t[1],t[2],t[0])))
 bad=sum(n!=2 for n in edges.values());volume=sum(sum(vs[a][k]*(vs[b][(k+1)%3]*vs[c][(k+2)%3]-vs[b][(k+2)%3]*vs[c][(k+1)%3]) for k in range(3)) for a,b,c in ts)/6
 print(label,len(ts),'triangles;',bad,'nonmanifold edges; volume',round(volume,4));assert bad==0 and volume>0
obj.find('metadata[@face_count]').set('face_count',str(len(model.findall('.//'+T('triangle')))))
cfg=json.loads(files['Metadata/project_settings.config']);cfg['filament_colour']=['#FFFFFF','#123E2B','#F4BE19','#101010'];cfg['filament_multi_colour']=cfg['filament_colour'];files['Metadata/project_settings.config']=json.dumps(cfg,indent=4).encode()
# Photograph references and cached hit-test maps must not represent the old model.
for plate in settings.findall('plate'):
 for m in list(plate):
  if m.get('key') in ('top_file','pick_file'):plate.remove(m)
for name in list(files):
 if name in ('Metadata/top_1.png','Metadata/pick_1.png') or name.startswith(('Auxiliaries/Model Pictures/','Auxiliaries/Profile Pictures/')):del files[name]
# Front-view preview generated directly from model triangles, supersampled.
objects={o.get('id'):o for o in model.findall('.//'+T('object'))};palette={'1':'#123E2B','2':'#FFFFFF','3':'#FFFFFF','5':'#F4BE19','6':'#101010','7':'#FFFFFF','8':'#123E2B','9':'#F4BE19'}
im=Image.new('RGB',(1500,2600),'#e9edf0');draw=ImageDraw.Draw(im);faces=[]
for comp in comps:
 key=comp.get('objectid');o=objects[key];m=list(map(float,comp.get('transform').split()));vs=[[float(v.get(a)) for a in ('x','y','z')] for v in o.findall('.//'+T('vertex'))];vs=[[sum(v[k]*m[k*3+j] for k in range(3))+m[9+j] for j in range(3)] for v in vs]
 for t in o.findall('.//'+T('triangle')):
  points=[vs[int(t.get(a))] for a in ('v1','v2','v3')];faces.append((sum(p[1] for p in points),[(750-p[2]*1.1*21,1300+p[0]*1.2*21) for p in points],palette[key]))
for _,pts,color in sorted(faces,key=lambda f:f[0]):draw.polygon(pts,fill=color)
im=im.resize((750,1300),Image.Resampling.LANCZOS);im.save(OUT/'EIE_Hockey_Tag_Logo_Vorschau.png');buf=io.BytesIO();im.save(buf,format='PNG')
for name in files:
 if name.endswith('.png'):files[name]=buf.getvalue()
for name,r in [('3D/Objects/object_1.model',model),('3D/3dmodel.model',main),('Metadata/model_settings.config',settings)]:files[name]=E.tostring(r,encoding='utf-8',xml_declaration=True)
with zipfile.ZipFile(OUT/'EIE_Hockey_Tag_mit_Logo.3mf','w',zipfile.ZIP_DEFLATED) as z:
 for n,data in files.items():z.writestr(n,data)
