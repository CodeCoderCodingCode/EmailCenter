import json,sys,os
sys.stdin.reconfigure(encoding="utf-8", errors="strict")
from pathlib import Path
root=Path(__file__).resolve().parents[1]
a=json.loads((root/'docs/localization/Catalog_Audit.json').read_text(encoding='utf-8'))
p=root/'docs/localization/Catalog_Review.json'
r=json.loads(p.read_text(encoding='utf-8'))
identities={'Deleted','Blocked','Preparing','Ready','Paused','Draft','Queued','Scheduled','Cancelled','Failed','Sending','Uncertain','Completed','Running','Sent','Imported','Valid','Word Replace','Website','Position','Status','Invalid','Pending','Skipped','Dismissed','Format','Pause','Details','Name','Job','Original','Text','HTML','PDF','DOCX','CSV','JSON','Excel','Gmail','Outbox','Builder','EmailCenter','Info','Error','Warning','Success','Debug','System','Windows','Export','Import','Video','Port','Optional','Standard','Logo','ID','Auto','Username','Password','Preview','Templates','Settings','Workspace','Projects','Dark','Light','Email','Offline','Online','Green','Blue','Terminal','Drafts','Application','Header','Footer','Normal','MIME','Table','Company','Contact'}
for i,e in enumerate(a):
 if e['source'] in identities:r.setdefault(str(i),e['source'])
for line in sys.stdin:
 line=line.rstrip('\r\n')
 if not line:continue
 i,value=line.split('|',1)
 assert i.isdigit(),line
 r[i]=value.replace('\\n','\n')
content=(json.dumps(r,ensure_ascii=False,indent=2)+'\n').encode('utf-8')
tmp=p.with_suffix('.tmp')
tmp.write_bytes(content)
os.replace(tmp,p)
print('Reviewed entries:',len(r))
