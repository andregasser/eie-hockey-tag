from pathlib import Path
import xml.etree.ElementTree as E,zipfile,json
import numpy as np
from shapely.geometry import Polygon
from shapely.ops import unary_union
ROOT=Path(__file__).resolve().parent.parent;N={'m':'http://schemas.microsoft.com/3dmanufacturing/core/2015/02'}
def read(path):
 with zipfile.ZipFile(path) as z:
  return E.fromstring(z.read('3D/3dmodel.model')),E.fromstring(z.read('3D/Objects/object_1.model')),E.fromstring(z.read('Metadata/model_settings.config'))
def xf(v,s):
 t=np.array(list(map(float,s.split())));return v@t[:9].reshape(3,3)+t[9:]
def parts(a,b):
 objects={o.get('id'):o for o in b.findall('.//m:object',N)};result={}
 for c in a.findall('.//m:component',N):
  o=objects[c.get('objectid')];v=np.array([[float(v.get(k)) for k in ('x','y','z')] for v in o.findall('.//m:vertex',N)]);t=np.array([[int(t.get(k)) for k in ('v1','v2','v3')] for t in o.findall('.//m:triangle',N)])
  result[c.get('objectid')]=(xf(v,c.get('transform')),t)
 return result
def footprint(v,t):
 polys=[]
 for tri in t:
  pts=v[tri][:,[2,0]]*np.array([-1.1,1.2]);p=Polygon(pts)
  if p.area>1e-10:polys.append(p)
 return unary_union(polys)
old=read(ROOT/'output/EIE_Hockey_Tag.3mf');new=read(ROOT/'output/EIE_Hockey_Tag_mit_Logo.3mf');op=parts(*old[:2]);np_=parts(*new[:2])
for key in op:
 assert np.array_equal(op[key][0],np_[key][0]) and np.array_equal(op[key][1],np_[key][1]),key
for key in ['2','3']:
 assert E.tostring(old[2].find(f".//part[@id='{key}']/text_info"))==E.tostring(new[2].find(f".//part[@id='{key}']/text_info"))
for label,data,ps in [('before',old,op),('after',new,np_)]:
 coords=np.concatenate([v for v,t in ps.values()]);world=xf(coords,data[0].find('.//m:item',N).get('transform'));print(label,'size mm',np.ptp(world,axis=0).round(6).tolist())
logo=unary_union([footprint(*np_[k]) for k in ['6','7','8','9']]);base=footprint(*np_['1']);name=footprint(*np_['2']);rim=footprint(*np_['5'])
assert logo.difference(base).area<1e-8
assert logo.intersection(name).area<1e-8
assert logo.intersection(rim).area<1e-8
print('Logo supported by base; name clearance mm',round(logo.distance(name),3),'rim clearance mm',round(logo.distance(rim),3))
print('Previous meshes and editable text metadata unchanged.')
