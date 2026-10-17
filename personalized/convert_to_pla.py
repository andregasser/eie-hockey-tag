from pathlib import Path
import zipfile,json,hashlib
ROOT=Path(__file__).resolve().parent.parent;OUT=ROOT/'output';profile={}
for n in ['fdm_filament_common','fdm_filament_pla','Generic PLA @base','Generic PLA @BBL A1']:
 profile.update(json.loads((ROOT/'profiles'/f'{n}.json').read_text()))
for who in ['SOPHIA_43','JASON_4']:
 with zipfile.ZipFile(OUT/f'EIE_{who}_v2.3mf') as z:files={n:z.read(n) for n in z.namelist()}
 old=json.loads(files['Metadata/project_settings.config']);cfg=old.copy();changed=[]
 # Apply the official resolved Generic PLA preset to existing filament fields.
 for k,v in profile.items():
  if k in cfg and isinstance(v,list) and len(v)==1 and isinstance(cfg[k],list) and len(cfg[k])==4:
   cfg[k]=v*4
   if old[k]!=cfg[k]:changed.append(k)
 cfg['filament_settings_id']=['Generic PLA @BBL A1']*4;cfg['filament_ids']=[profile['filament_id']]*4
 cfg['different_settings_to_system']=['']*len(cfg['different_settings_to_system'])
 # Retired PETG-specific fan lead times are not part of the current PLA preset.
 cfg['pre_start_fan_time']=['0']*4
 for n in list(files):
  if n.startswith('Metadata/filament_settings_'):del files[n]
 files['Metadata/project_settings.config']=json.dumps(cfg,indent=4).encode()
 target=OUT/f'EIE_{who}_v2_PLA.3mf'
 with zipfile.ZipFile(target,'w',zipfile.ZIP_DEFLATED) as z:
  for n,data in files.items():z.writestr(n,data)
 with zipfile.ZipFile(target) as z,zipfile.ZipFile(OUT/f'EIE_{who}_v2.3mf') as source:
  for n in ['3D/Objects/object_1.model','3D/3dmodel.model','Metadata/model_settings.config']:assert z.read(n)==source.read(n)
  actual=json.loads(z.read('Metadata/project_settings.config'))
  assert actual['filament_type']==['PLA']*4
  assert actual['nozzle_temperature']==['220']*4 and actual['textured_plate_temp']==['65']*4
  assert actual['filament_max_volumetric_speed']==['12']*4
  assert 'PETG' not in z.read('Metadata/project_settings.config').decode()
 print(who,'updated',len(changed),'filament fields; unchanged geometry; PLA settings verified.')
(ROOT/'profiles/PLA_conversion_notes.json').write_text(json.dumps({'profile':'Generic PLA @BBL A1','source':'https://github.com/bambulab/BambuStudio/tree/master/resources/profiles/BBL/filament','changed_keys':changed,'nozzle':220,'bed_textured':65,'flow_ratio':.98,'max_volumetric_speed':12,'fan_min':60,'fan_max':80},indent=2))
