from pathlib import Path
import zipfile,json,xml.etree.ElementTree as E,collections,io
from PIL import Image,ImageDraw
ROOT=Path(__file__).resolve().parent.parent;OUT=ROOT/'output'
NS='http://schemas.microsoft.com/3dmanufacturing/core/2015/02';P='http://schemas.microsoft.com/3dmanufacturing/production/2015/06';T=lambda n:'{'+NS+'}'+n
E.register_namespace('',NS);E.register_namespace('p',P)
with zipfile.ZipFile(OUT/'EIE_Hockey_Tag_mit_Logo.3mf') as z:files={n:z.read(n) for n in z.namelist()}
model=E.fromstring(files['3D/Objects/object_1.model']);main=E.fromstring(files['3D/3dmodel.model']);settings=E.fromstring(files['Metadata/model_settings.config']);obj=settings.find('object');comps=main.find('.//'+T('components'))
texts=json.loads((ROOT/'typography/text-mesh.json').read_text())
for key,height,cy in [('2',10,-12.5),('3',25,11.527584756)]:
 data=texts[key];v=data['v'];ts=data['t'];lo=[min(p[i] for p in v) for i in range(3)];hi=[max(p[i] for p in v) for i in range(3)];factor=height/(hi[1]-lo[1]);width=(hi[0]-lo[0])*factor
 assert width<46
 # Use uniform planar scaling; normalize inherited component scales to physical millimetres.
 v=[[(p[0]-(lo[0]+hi[0])/2)*factor,(p[1]-(lo[1]+hi[1])/2)*factor,-.0149999997+(p[2]-lo[2])/(hi[2]-lo[2])*(.785000026+.0149999997)] for p in v]
 o=model.find(".//"+T('object')+"[@id='"+key+"']");o.remove(o.find(T('mesh')));mesh=E.SubElement(o,T('mesh'));vr=E.SubElement(mesh,T('vertices'));tr=E.SubElement(mesh,T('triangles'))
 for p in v:E.SubElement(vr,T('vertex'),{a:format(n,'.12g') for a,n in zip(('x','y','z'),p)})
 for t in ts:E.SubElement(tr,T('triangle'),{a:str(n) for a,n in zip(('v1','v2','v3'),t)})
 comp=next(c for c in comps if c.get('objectid')==key);ty=float(comp.get('transform').split()[10]);tx=cy/1.2
 transform=[0,0,-1/1.1,-1/1.2,0,0,0,2,0,tx,ty,0];comp.set('transform',' '.join(format(x,'.16g') for x in transform))
 part=obj.find(f"part[@id='{key}']");part.find("metadata[@key='matrix']").set('value',' '.join(format(x,'.16g') for x in [0,-1/1.2,0,tx,0,0,2,ty,-1/1.1,0,0,0,0,0,0,1]))
 info=part.find('text_info');info.set('font_name','College');info.set('font_version','1.0');info.set('style_name','Bold');info.set('bold','1');info.set('font_size',format(factor,'.8g'));part.find('mesh_stat').set('face_count',str(len(ts)))
 # Blender's cap vertices are duplicated: weld by coordinate for topology validation.
 weld={};ids=[]
 for p in v:
  q=tuple(round(n,7) for n in p)
  if q not in weld:weld[q]=len(weld)
  ids.append(weld[q])
 edges=collections.Counter(tuple(sorted((ids[a],ids[b]))) for t in ts for a,b in zip(t,(t[1],t[2],t[0])))
 bad=sum(n!=2 for n in edges.values());assert bad==0
 print('Name' if key=='2' else 'Number','size',round(width,3),height,'mm; font size',factor,'nonmanifold',bad)
obj.find('metadata[@face_count]').set('face_count',str(len(model.findall('.//'+T('triangle')))))
# Actual mesh preview.
objects={o.get('id'):o for o in model.findall('.//'+T('object'))};palette={'1':'#123E2B','2':'#FFFFFF','3':'#FFFFFF','5':'#F4BE19','6':'#101010','7':'#FFFFFF','8':'#123E2B','9':'#F4BE19'}
im=Image.new('RGB',(1500,2600),'#e9edf0');draw=ImageDraw.Draw(im);faces=[]
for comp in comps:
 key=comp.get('objectid');o=objects[key];m=list(map(float,comp.get('transform').split()));vs=[[float(v.get(a)) for a in ('x','y','z')] for v in o.findall('.//'+T('vertex'))];vs=[[sum(v[k]*m[k*3+j] for k in range(3))+m[9+j] for j in range(3)] for v in vs]
 for t in o.findall('.//'+T('triangle')):
  points=[vs[int(t.get(a))] for a in ('v1','v2','v3')];faces.append((sum(p[1] for p in points),[(750-p[2]*1.1*21,1300+p[0]*1.2*21) for p in points],palette[key]))
for _,pts,color in sorted(faces,key=lambda f:f[0]):draw.polygon(pts,fill=color)
im=im.resize((750,1300),Image.Resampling.LANCZOS);im.save(OUT/'EIE_Hockey_Tag_Schrift_v2_Vorschau.png');buf=io.BytesIO();im.save(buf,format='PNG')
for name in files:
 if name.endswith('.png'):files[name]=buf.getvalue()
for name,r in [('3D/Objects/object_1.model',model),('3D/3dmodel.model',main),('Metadata/model_settings.config',settings)]:files[name]=E.tostring(r,encoding='utf-8',xml_declaration=True)
with zipfile.ZipFile(OUT/'EIE_Hockey_Tag_Schrift_v2.3mf','w',zipfile.ZIP_DEFLATED) as z:
 for n,data in files.items():z.writestr(n,data)
