from pathlib import Path
import cv2,numpy as np,json
from shapely.geometry import Polygon,MultiPolygon,GeometryCollection
from shapely.ops import unary_union
from shapely import make_valid
ROOT=Path(__file__).resolve().parent
img=cv2.imread('/home/andre/.codex/attachments/fe2a90c9-2911-414c-9327-3167e58ee910/IMG_3278_1792224198038.heic.jpg')
img=cv2.resize(img,(1200,round(img.shape[0]*1200/img.shape[1])))
img=cv2.medianBlur(img,5);b,g,r=cv2.split(img.astype(float))
yellow=(r>120)&(g>75)&(r>g*1.15)&(g>b*1.65)
white=(r+g+b)/3>125
sil=(~white)|yellow
contours,_=cv2.findContours(sil.astype('uint8'),cv2.RETR_EXTERNAL,cv2.CHAIN_APPROX_SIMPLE)
c=max(contours,key=cv2.contourArea);mask=np.zeros(img.shape[:2],np.uint8);cv2.drawContours(mask,[c],-1,1,-1)
labels=np.zeros(img.shape[:2],np.uint8)
labels[(g>r+2)&(~white)]=2
labels[yellow]=3
labels[white&(~yellow)]=1
labels[mask==0]=4
palette=np.array([[15,15,15],[255,255,255],[43,62,18],[25,190,244],[240,237,233]],np.uint8)
cv2.imwrite(str(ROOT/'segmentation.png'),palette[labels])
# Extract each region with holes. Contours are smoothed in physical units below.
x,y,w,h=cv2.boundingRect(c);scale=22.2/h
print('Silhouette source bounds',x,y,w,h,'width mm',w*scale,'height mm',h*scale)
def polygons(binary):
 cs,hh=cv2.findContours(binary.astype('uint8'),cv2.RETR_CCOMP,cv2.CHAIN_APPROX_SIMPLE)
 result=[]
 if hh is None:return GeometryCollection()
 def ring(c):return [(float(p[0][0]-x)*scale,float(p[0][1]-y)*scale) for p in c]
 for i,cc in enumerate(cs):
  if hh[0,i,3]!=-1 or len(cc)<3:continue
  holes=[];child=hh[0,i,2]
  while child!=-1:
   if len(cs[child])>=3:holes.append(ring(cs[child]))
   child=hh[0,child,0]
  p=make_valid(Polygon(ring(cc),holes))
  if p.area>.015:result.append(p)
 return unary_union(result)
silhouette=polygons(mask).simplify(.04,preserve_topology=True)
# White and yellow detail shapes, with mild closing to suppress photographic noise.
regions={}
for color in [1,3,2]:
 p=polygons((labels==color)&(mask!=0)).simplify(.035,preserve_topology=True)
 p=p.intersection(silhouette)
 for other in regions.values():p=p.difference(other)
 regions[color]=p
regions[0]=silhouette.difference(unary_union(list(regions.values())))
def pieces(p):
 if isinstance(p,Polygon):return [p]
 return [q for z in getattr(p,'geoms',[]) for q in pieces(z)]
# Discard tiny isolated photographic specks; black fills the freed area.
for color in [1,2,3]:regions[color]=unary_union([p for p in pieces(regions[color]) if p.area>=.015])
regions[0]=silhouette.difference(unary_union([regions[c] for c in [1,2,3]]))
result={str(k):[{'outer':list(p.exterior.coords)[:-1],'holes':[list(r.coords)[:-1] for r in p.interiors]} for p in pieces(v)] for k,v in regions.items()}
json.dump({'width':w*scale,'height':22.2,'regions':result},open(ROOT/'logo_vectors.json','w'))
# SVG is the vector master; the photo is not embedded in the printable model.
colors={0:'#101010',1:'#ffffff',2:'#123e2b',3:'#f4be19'}
s=[f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="-0.3 -0.3 {w*scale+.6} 22.8">']
for k in [0,2,3,1]:
 for p in result[str(k)]:
  d=' '.join('M '+' L '.join(f'{a:.5f},{b:.5f}' for a,b in ring)+' Z' for ring in [p['outer']]+p['holes'])
  s.append(f'<path fill="{colors[k]}" fill-rule="evenodd" d="{d}"/>')
s.append('</svg>');(ROOT/'EIE_Logo.svg').write_text('\n'.join(s))
print('Region areas mm2', {k:round(v.area,2) for k,v in regions.items()})
