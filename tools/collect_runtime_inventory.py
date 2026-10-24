"""Collect installed runtime metadata and shipped notices without network access."""
from pathlib import Path
from importlib.metadata import distribution
import hashlib,json,platform,re,shutil,sqlite3
from pip._vendor.packaging.requirements import Requirement

ROOT=Path(__file__).resolve().parents[1]

def main():
    queue=[Requirement(line.strip()) for line in (ROOT/'requirements.txt').read_text().splitlines() if line.strip() and not line.lstrip().startswith('#')]
    packages={};output=ROOT/'docs/third_party';output.mkdir(exist_ok=True)
    while queue:
        requested=queue.pop(0)
        if requested.marker and not requested.marker.evaluate({'extra':''}):continue
        dist=distribution(requested.name);meta=dist.metadata;name=meta['Name'];key=name.casefold().replace('_','-')
        if dist.version not in requested.specifier:
            raise RuntimeError(f'Installed version does not match {requested}')
        if key in packages:continue
        classifiers=meta.get_all('Classifier') or []
        license_name=meta.get('License-Expression') or meta.get('License') or next((c.rsplit(' :: ',1)[1] for c in classifiers if c.startswith('License :: ')),'Not declared')
        row={'name':name,'version':dist.version,'license_metadata':license_name,'requires_python':meta.get('Requires-Python'),'project_urls':meta.get_all('Project-URL') or [],'requirements':meta.get_all('Requires-Dist') or [],'notices':[]}
        folder=output/re.sub(r'[^a-zA-Z0-9._-]','_',name);folder.mkdir(exist_ok=True)
        for entry in dist.files or []:
            if not any(token in str(entry).lower() for token in ('license','licence','notice')):continue
            source=Path(dist.locate_file(entry))
            if not source.is_file():continue
            content=source.read_bytes();digest=hashlib.sha256(content).hexdigest();target=folder/(digest[:8]+'-'+source.name)
            target.write_bytes(content);row['notices'].append({'path':target.relative_to(ROOT).as_posix(),'sha256':digest,'size':len(content)})
        packages[key]=row
        queue.extend(Requirement(value) for value in row['requirements'])
    converter=ROOT/'.tools/libreoffice'
    if converter.is_dir():
        folder=output/'LibreOffice';folder.mkdir(exist_ok=True)
        for name in ('LICENSE.html','license.txt','NOTICE'):
            if (converter/name).is_file():shutil.copyfile(converter/name,folder/name)
    result={'format_version':1,'runtime':{'python':platform.python_version(),'windows':platform.platform(),'architecture':platform.machine(),'sqlite':sqlite3.sqlite_version},'requirements_match':True,'packages':sorted(packages.values(),key=lambda r:r['name'].lower()),'missing_shipped_notice_files':[row['name'] for row in packages.values() if not row['notices']]}
    (ROOT/'docs/Runtime_Inventory.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
    print(f'{len(packages)} runtime packages verified; {sum(len(row["notices"]) for row in packages.values())} shipped notice files collected.')
    print('No shipped notice file:',', '.join(result['missing_shipped_notice_files']))

if __name__=='__main__':main()
