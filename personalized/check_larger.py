from pathlib import Path
exec(Path('logo/check_logo.py').read_text().split('old=read(')[0].replace('ROOT=Path(__file__).resolve().parent.parent','ROOT=Path.cwd()'))
source=read(ROOT/'output/EIE_Hockey_Tag_Schrift_v2.3mf');sp=parts(*source[:2]);coords=np.concatenate([v for v,t in sp.values()]);sw=xf(coords,source[0].find('.//m:item',N).get('transform'));expected=np.ptp(sw,axis=0)
base=footprint(*sp['1']);rim=footprint(*sp['5']);logo=unary_union([footprint(*sp[k]) for k in ['6','7','8','9']])
for label in ['SOPHIA_43','JASON_4']:
 data=read(ROOT/f'output/EIE_{label}_v2.3mf');p=parts(*data[:2])
 for k in ['1','5','6','7','8','9']:assert np.array_equal(sp[k][0],p[k][0]) and np.array_equal(sp[k][1],p[k][1])
 coords=np.concatenate([v for v,t in p.values()]);w=xf(coords,data[0].find('.//m:item',N).get('transform'));assert np.allclose(np.ptp(w,axis=0),expected,atol=1e-8)
 shapes={k:footprint(*p[k]) for k in ['2','3','10','11']};text=unary_union(list(shapes.values()))
 assert text.difference(base).area<1e-8
 assert text.intersection(rim).area<1e-8 and text.intersection(logo).area<1e-8
 for k,l in [('2','10'),('3','11')]:assert shapes[k].intersection(shapes[l]).area<1e-8
 assert data[2].find('.//text_info') is None
 print(label,'size',np.ptp(w,axis=0).round(6).tolist(),'logo clearance',round(text.distance(logo),3),'mm; checks passed')
