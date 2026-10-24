"""Build an allowlisted Windows distribution, including public Desktop OAuth config."""
from pathlib import Path
import hashlib
import json
import os
import shutil
import subprocess
import sys
from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/'src'))
from emailcenter.resources import shared_oauth_client
from emailcenter.gmail import load_desktop_client
from windows_release_layout import validate_bundle, retire_intermediate_executable

PACK = ROOT/'packaging'
logo = Image.open(ROOT/'assets/Logo256.png').convert('RGBA')
logo.save(PACK/'EmailCenter.ico', sizes=[(16,16),(32,32),(48,48),(64,64),(128,128),(256,256)])
for name, size in [('wizard.bmp',(164,314)),('wizard-small.bmp',(55,55))]:
    background = Image.new('RGB', size, '#132438')
    icon_size = 104 if size[0]>100 else 42
    icon = logo.resize((icon_size,icon_size), Image.Resampling.NEAREST)
    background.paste(icon, ((size[0]-icon_size)//2,35 if size[0]>100 else 6), icon)
    if size[0]>100:
        draw=ImageDraw.Draw(background)
        font=ImageFont.truetype('C:/Windows/Fonts/segoeuib.ttf',18)
        small=ImageFont.truetype('C:/Windows/Fonts/segoeui.ttf',12)
        draw.text((16,168),'EmailCenter',font=font,fill='white')
        draw.multiline_text((16,204),'Bewerbungen\nDokumente\nE-Mails',font=small,fill='#cbdbee',spacing=10)
    background.save(PACK/name)

command=[sys.executable,'-m','PyInstaller','--noconfirm','--clean','--name','EmailCenter','--windowed','--onedir',
         '--paths',str(ROOT/'src'),'--distpath',str(ROOT/'dist/runtime'),'--workpath',str(ROOT/'build/pyinstaller'),'--specpath',str(ROOT/'build'),
         '--icon',str(PACK/'EmailCenter.ico'),'--version-file',str(PACK/'version.txt'),
         '--hidden-import','keyring.backends.Windows','--collect-data','tzdata',
         '--runtime-hook',str(PACK/'qt_runtime_hook.py'),
         '--add-data',str(ROOT/'migrations')+';migrations',
         '--add-data',str(ROOT/'assets/Logo256.png')+';assets',
         '--add-data',str(ROOT/'assets/templates')+';assets/templates',
         '--add-data',str(ROOT/'guide/EmailCenter_Guide.html')+';guide',
         '--add-data',str(ROOT/'docs/third_party')+';licenses',str(ROOT/'start_emailcenter.py')]
windows=Path(os.environ.get('WINDIR','C:/Windows'))
environment={**os.environ,'PATH':os.pathsep.join((str(Path(sys.base_prefix)),str(Path(sys.base_prefix)/'DLLs'),str(ROOT/'.venv/Scripts'),str(windows/'System32'),str(windows)))}
subprocess.run(command,cwd=ROOT,env=environment,check=True)
runtime=ROOT/'dist/runtime/EmailCenter/_internal'
qt_runtime=ROOT/'.venv/Lib/site-packages/PySide6'
# Python's older VC runtime must not shadow the runtime required by Qt. Keep
# one compatible family at the loader's root, without changing Windows DLLs.
for pattern in ('vcruntime140*.dll','msvcp140*.dll','concrt140.dll'):
    for file in qt_runtime.glob(pattern):
        shutil.copy2(file,runtime/file.name)
# Qt uses Windows' unversioned ICU. Artifact tooling on PATH may expose a
# different ICU ABI (e.g. Poppler's _78 exports); it must not shadow Windows.
for name in ('icuuc.dll','icudt78.dll'):
    (runtime/name).unlink(missing_ok=True)
converter=ROOT/'.tools/libreoffice'
if not (converter/'program/soffice.com').is_file():
    raise RuntimeError('Portable LibreOffice must be available before release.')
shutil.copytree(converter,runtime/'LibreOffice',dirs_exist_ok=True,ignore=shutil.ignore_patterns('*.msi','*.log'))
# Only the Desktop application's configuration is shipped. No authorized-user
# records, refresh/access tokens, vault content or source JSON directory.
source=shared_oauth_client()
if source is None:
    raise RuntimeError('Shared Desktop OAuth client missing.')
configuration=load_desktop_client(source)['installed']
allowed=('client_id','project_id','auth_uri','token_uri','auth_provider_x509_cert_url','client_secret','redirect_uris')
oauth=runtime/'assets/oauth/desktop_client.json'
oauth.parent.mkdir(parents=True,exist_ok=True)
oauth.write_text(json.dumps({'installed':{k:configuration[k] for k in allowed if k in configuration}},indent=2),encoding='utf-8')
for name in ('Welcome.txt','Finish.txt','LICENSE.txt'):
    shutil.copy2(PACK/name,runtime/'licenses'/name)
shutil.copy2(ROOT/'docs/Runtime_Inventory.json',runtime/'licenses/Runtime_Inventory.json')
validate_bundle(runtime.parent)
retire_intermediate_executable(ROOT)
compiler=ROOT/'.tools/inno/ISCC.exe'
if '--runtime-only' in sys.argv:
    print('Runtime assembled; installer compilation deferred for validation.')
    raise SystemExit(0)
subprocess.run([str(compiler),str(PACK/'EmailCenter.iss')],cwd=ROOT,check=True)
setup=ROOT/'dist/release/EmailCenter-Setup-1.0.1-Windows-x64.exe'
manifest={'version':'1.0.1','installer':setup.name,'size':setup.stat().st_size,'sha256':hashlib.file_digest(setup.open('rb'),'sha256').hexdigest(),'shared_desktop_client':True,'user_tokens_included':False}
(setup.parent/'Release.json').write_text(json.dumps(manifest,indent=2),encoding='utf-8')
shutil.copy2(ROOT/'guide/EmailCenter_Guide.html', setup.parent/'EmailCenter_Guide.html')
print(json.dumps(manifest,indent=2))
