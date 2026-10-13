"""Read-only check of the shared Manim, TeX and media deployment."""
from pathlib import Path
import json,os,subprocess,sys
root=Path(os.environ.get('CODEX_HOME') or Path.home()/'.codex')/'runtimes/personal-video'
commands={'manim':[root/'manim/venv/Scripts/python.exe','-B','-m','manim','--version'],
          'latex':[root/'manim/TinyTeX/bin/windows/latex.exe','--version'],
          'dvisvgm':[root/'manim/TinyTeX/bin/windows/dvisvgm.exe','--version'],
          'ffmpeg':[root/'native/ffmpeg/ffmpeg.exe','-version']}
checks={'python_supported':sys.version_info >= (3,11)}
versions={}
for name,argv in commands.items():
    try:
        result=subprocess.run([str(x) for x in argv],capture_output=True,text=True,encoding='utf-8',errors='replace',timeout=30)
        checks[name]=result.returncode==0
        versions[name]=(result.stdout or result.stderr).splitlines()[0]
    except (OSError,subprocess.TimeoutExpired):
        checks[name]=False
print(json.dumps({'passed':all(checks.values()),'checks':checks,'versions':versions,'missing':[k for k,v in checks.items() if not v]}))
raise SystemExit(0 if all(checks.values()) else 1)
