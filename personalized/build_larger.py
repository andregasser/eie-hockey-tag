from pathlib import Path
import zipfile,json,xml.etree.ElementTree as E,collections,io
import numpy as np,mapbox_earcut as earcut
from shapely.geometry import Polygon
from shapely.geometry.polygon import orient
from shapely.ops import unary_union
from shapely import affinity
from PIL import Image,ImageDraw
ROOT=Path(__file__).resolve().parent.parent;OUT=ROOT/'output';NS='http://schemas.microsoft.com/3dmanufacturing/core/2015/02';P='http://schemas.microsoft.com/3dmanufacturing/production/2015/06';T=lambda n:'{'+NS+'}'+n
E.register_namespace('',NS);E.register_namespace('p',P)
with zipfile.ZipFile(OUT/'EIE_Hockey_Tag_Schrift_v2.3mf') as z:original={n:z.read(n) for n in z.namelist()}
texts=json.loads((ROOT/'personalized/text-mesh.json').read_text())
BASE=3.4289999;TOP=4.491002442
IDENTITY='1 0 0 0 1 0 0 0 1 0 0 0';MATRIX='1 0 0 0 0 1 0 0 0 0 1 0 0 0 0 1'
def pieces(p):
 if isinstance(p,Polygon):return [p]
 return [q for a in p.geoms for q in pieces(a)]
def clean(r):
 pts=list(r.coords)[:-1]
 while True:
  new=[]
  for i,b in enumerate(pts):
   a=pts[i-1];c=pts[(i+1)%len(pts)]
   if abs((b[0]-a[0])*(c[1]-b[1])-(b[1]-a[1])*(c[0]-b[0]))>1e-10:new.append(b)
  if len(new)==len(pts):return new
  assert len(new)>=3
  pts=new

def lettering(text,maxheight,maxwidth,cy):
 data=texts[text];v=np.array(data['v']);cap=max(v[:,2]);polys=[]
 for t in data['t']:
  q=v[t]
  if np.max(np.abs(q[:,2]-cap))<1e-7:
   p=Polygon(q[:,:2])
   if p.area>1e-12:polys.append(p)
 p=unary_union(polys).simplify(1e-7);a,b,c,d=p.bounds;factor=min(maxheight/(d-b),maxwidth/(c-a))
 p=affinity.translate(p,-(a+c)/2,-(b+d)/2);p=affinity.scale(p,xfact=factor,yfact=-factor,origin=(0,0));p=affinity.translate(p,yoff=cy)
 # Widen numeral strokes by 0.9 mm in addition to the larger character size.
 if text.isdigit():p=p.buffer(.45,join_style=2)
 return p

def extrude(shape):
 vertices=[];triangles=[]
 for poly in pieces(shape.buffer(-.0001,join_style=2)):
  poly=orient(poly,sign=1);rings=[clean(poly.exterior)]+[clean(r) for r in poly.interiors];coords=np.array([p for r in rings for p in r]);n=len(coords);start=len(vertices)
  faces=earcut.triangulate_float64(coords,np.cumsum([len(r) for r in rings],dtype=np.uint32)).reshape(-1,3);local=[];cap_edges=[];cap_area=0
  for h in [BASE,TOP]:
   vertices.extend((y/1.2,h,-x/1.1) for x,y in coords)
  for a,b,c in faces:
   u=coords[b]-coords[a];v=coords[c]-coords[a]
   if u[0]*v[1]-u[1]*v[0]<0:b,c=c,b
   local.extend([(int(a),int(c),int(b)),(int(a+n),int(b+n),int(c+n))])
   cap_edges.extend([(int(a),int(b)),(int(b),int(c)),(int(c),int(a))]);cap_area+=abs(u[0]*v[1]-u[1]*v[0])/2
  assert abs(cap_area-poly.area)<1e-7
  counts=collections.Counter(tuple(sorted(e)) for e in cap_edges)
  for a,b in cap_edges:
   if counts[tuple(sorted((a,b)))]==1:local.extend([(a,b,b+n),(a,b+n,a+n)])
  triangles.extend((start+a,start+c,start+b) for a,b,c in local)
 edges=collections.Counter(tuple(sorted((a,b))) for t in triangles for a,b in zip(t,(t[1],t[2],t[0])))
 assert all(n==2 for n in edges.values()),'Mesh edge error'
 volume=sum(sum(vertices[a][k]*(vertices[b][(k+1)%3]*vertices[c][(k+2)%3]-vertices[b][(k+2)%3]*vertices[c][(k+1)%3]) for k in range(3)) for a,b,c in triangles)/6
 assert volume>0
 return vertices,triangles

def setmesh(model,key,v,t):
 o=model.find('.//'+T('object')+f"[@id='{key}']")
 if o is None:o=E.SubElement(model.find(T('resources')),T('object'),{'id':key,'type':'model'})
 else:o.remove(o.find(T('mesh')))
 mesh=E.SubElement(o,T('mesh'));vr=E.SubElement(mesh,T('vertices'));tr=E.SubElement(mesh,T('triangles'))
 for p in v:E.SubElement(vr,T('vertex'),{a:format(float(n),'.12g') for a,n in zip(('x','y','z'),p)})
 for p in t:E.SubElement(tr,T('triangle'),{a:str(n) for a,n in zip(('v1','v2','v3'),p)})

def render(model,main,path):
 objects={o.get('id'):o for o in model.findall('.//'+T('object'))};palette={'1':'#123E2B','2':'#FFFFFF','3':'#FFFFFF','5':'#F4BE19','6':'#101010','7':'#FFFFFF','8':'#123E2B','9':'#F4BE19','10':'#F4BE19','11':'#F4BE19'}
 im=Image.new('RGB',(1500,2600),'#e9edf0');d=ImageDraw.Draw(im);faces=[]
 for comp in main.findall('.//'+T('component')):
  key=comp.get('objectid');o=objects[key];m=np.array(list(map(float,comp.get('transform').split())));v=np.array([[float(v.get(a)) for a in ('x','y','z')] for v in o.findall('.//'+T('vertex'))]);v=v@m[:9].reshape(3,3)+m[9:]
  for t in o.findall('.//'+T('triangle')):
   points=v[[int(t.get(a)) for a in ('v1','v2','v3')]];faces.append((sum(p[1] for p in points),[(750-p[2]*1.1*21,1300+p[0]*1.2*21) for p in points],palette[key]))
 for _,pts,color in sorted(faces,key=lambda a:a[0]):d.polygon(pts,fill=color)
 im=im.resize((750,1300),Image.Resampling.LANCZOS);im.save(path);buf=io.BytesIO();im.save(buf,format='PNG');return im,buf.getvalue()
previews=[]
for name,number in [('SOPHIA','43'),('JASON','4')]:
 files=original.copy();model=E.fromstring(files['3D/Objects/object_1.model']);main=E.fromstring(files['3D/3dmodel.model']);settings=E.fromstring(files['Metadata/model_settings.config']);obj=settings.find('object');comps=main.find('.//'+T('components'))
 title=f'EIE {name} {number}';obj.find("metadata[@key='name']").set('value',title)
 for meta in main.findall(T('metadata')):
  if meta.get('name')=='Title':meta.text=title
 shapes=[]
 for key,borderkey,text,height,maxwidth,cy,width,label in [('2','10',name,11,44.4,-10.8,.5,'Name'),('3','11',number,30,40,15.5,.6,'Nummer')]:
  white=lettering(text,height,maxwidth,cy);outline=white.buffer(width,join_style=2).difference(white);assert outline.intersection(white).area<1e-8
  shapes.append(white.union(outline))
  print(name,number,label,text,'white bounds',tuple(round(x,3) for x in white.bounds))
  for id_,shape,filament,partname in [(key,white,'1',f'{label} {text} – Weiss'),(borderkey,outline,'3',f'{label} {text} – Gelbe Kontur')]:
   v,t=extrude(shape);setmesh(model,id_,v,t);part=obj.find(f"part[@id='{id_}']")
   if part is None:part=E.SubElement(obj,'part',{'id':id_,'subtype':'normal_part'})
   else:
    for child in list(part):part.remove(child)
   for k,val in [('name',partname),('extruder',filament),('matrix',MATRIX)]:E.SubElement(part,'metadata',{'key':k,'value':val})
   E.SubElement(part,'mesh_stat',{'face_count':str(len(t))})
   comp=next((c for c in comps if c.get('objectid')==id_),None)
   if comp is None:comp=E.SubElement(comps,T('component'),{'{'+P+'}path':'/3D/Objects/object_1.model','objectid':id_})
   comp.set('transform',IDENTITY)
 obj.find('metadata[@face_count]').set('face_count',str(len(model.findall('.//'+T('triangle')))))
 assert shapes[0].distance(shapes[1])>3
 stem=f'EIE_{name}_{number}_v2';im,png=render(model,main,OUT/f'{stem}_Vorschau.png');previews.append(im)
 for n in files:
  if n.endswith('.png'):files[n]=png
 for n,r in [('3D/Objects/object_1.model',model),('3D/3dmodel.model',main),('Metadata/model_settings.config',settings)]:files[n]=E.tostring(r,encoding='utf-8',xml_declaration=True)
 with zipfile.ZipFile(OUT/f'{stem}.3mf','w',zipfile.ZIP_DEFLATED) as z:
  for n,data in files.items():z.writestr(n,data)
comparison=Image.new('RGB',(1500,1300),'#e9edf0')
for i,im in enumerate(previews):comparison.paste(im,(750*i,0))
comparison.save(OUT/'SOPHIA_43_JASON_4_v2_Vorschau.png')
