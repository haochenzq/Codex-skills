"""Reusable local entry: actual Remotion CLI and existing video-use helpers.

No credentials are read; no media API is called. Dependency installation is explicit,
outside this entry. Every command uses project tools and a subprocess-only PATH.
"""
from pathlib import Path
import argparse
import importlib.util
import json
import math
import os
import subprocess
import sys
import hashlib

ROOT = Path(__file__).resolve().parent
PROJECT = ROOT.parent
REMOTION = ROOT / 'remotion'
NODE = Path('C:/Program Files/nodejs/node.exe')
PYTHON = Path('C:/Users/lenovo/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/python.exe')
EDGE = Path('C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe')
RENDER_BROWSER = REMOTION / 'node_modules/.remotion/chrome-headless-shell/win64/chrome-headless-shell-win64/chrome-headless-shell.exe'
CODEX_DIR = Path(os.environ.get('CODEX_HOME') or Path.home() / '.codex')
HELPERS = CODEX_DIR / 'skills/video-use/helpers'
FFMPEG = PROJECT / 'native' / 'ffmpeg'


def environment():
    env = os.environ.copy()
    env['PATH'] = str(FFMPEG) + os.pathsep + str(NODE.parent) + os.pathsep + env.get('PATH', '')
    env['PYTHONUTF8'] = '1'
    env['PYTHONIOENCODING'] = 'utf-8'
    return env


def remotion_cli():
    package = REMOTION / 'node_modules' / '@remotion' / 'cli' / 'package.json'
    info = json.loads(package.read_text(encoding='utf-8'))
    binary = info['bin']
    relative = binary['remotion'] if isinstance(binary, dict) else binary
    return [str(NODE), str(package.parent / relative)]


def remotion_browser():
    if not RENDER_BROWSER.is_file():
        raise ValueError('Shared Chrome Headless Shell is missing; repair the maintained runtime before rendering')
    return str(RENDER_BROWSER)


def invoke(argv, cwd=None):
    return subprocess.run([str(x) for x in argv], cwd=cwd, env=environment(), check=True).returncode


def doctor():
    paths = {'python': PYTHON, 'node': NODE, 'browser': RENDER_BROWSER,
             'ffmpeg': FFMPEG / 'ffmpeg.exe', 'ffprobe': FFMPEG / 'ffprobe.exe',
             'video_use_render': HELPERS / 'render.py', 'video_use_timeline': HELPERS / 'timeline_view.py',
             'manim_python': CODEX_DIR/'runtimes/personal-video/manim/venv/Scripts/python.exe',
             'latex': CODEX_DIR/'runtimes/personal-video/manim/TinyTeX/bin/windows/latex.exe',
             'dvisvgm': CODEX_DIR/'runtimes/personal-video/manim/TinyTeX/bin/windows/dvisvgm.exe',
             'remotion_package': REMOTION / 'node_modules' / 'remotion' / 'package.json',
             'remotion_three_package': REMOTION / 'node_modules/@remotion/three/package.json',
             'three_package': REMOTION / 'node_modules/three/package.json',
             'fiber_package': REMOTION / 'node_modules/@react-three/fiber/package.json'}
    report = {k: {'path': str(v), 'exists': v.is_file()} for k,v in paths.items()}
    if paths['remotion_package'].is_file():
        report['remotion_version'] = json.loads(paths['remotion_package'].read_text(encoding='utf-8'))['version']
    manifest = json.loads((REMOTION / 'package.json').read_text(encoding='utf-8'))['dependencies']
    versions = {name: json.loads((REMOTION / 'node_modules' / name / 'package.json').read_text(encoding='utf-8'))['version']
                for name in ('@remotion/three', 'three', '@react-three/fiber', 'react')
                if (REMOTION / 'node_modules' / name / 'package.json').is_file()}
    report['remotion_3d_versions'] = versions
    report['remotion_3d_ready'] = (all(versions.get(n) == manifest.get(n) for n in ('@remotion/three', 'three', '@react-three/fiber', 'react'))
                                  and versions.get('@remotion/three') == report.get('remotion_version'))
    from blender_tools import dependency_status
    report['blender'] = dependency_status()
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report['remotion_3d_ready'] and all(x['exists'] for x in report.values() if isinstance(x,dict) and 'exists' in x) else 1


def load_video_use():
    # Reuse original upstream code, with two narrowly scoped Windows adapters.
    sys.path.insert(0, str(HELPERS))
    spec = importlib.util.spec_from_file_location('video_use_render', HELPERS / 'render.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    def concat_segments(segment_paths, out_path, edit_dir):
        concat_list = edit_dir / '_concat.txt'
        def quote(p):
            return p.resolve().as_posix().replace("'", "'\\''")
        concat_list.write_text(''.join(f"file '{quote(p)}'\n" for p in segment_paths), encoding='utf-8')
        print(f'video-use concat → {out_path.name}', flush=True)
        module.run(['ffmpeg','-hide_banner','-loglevel','warning','-y','-f','concat','-safe','0',
                    '-i',str(concat_list),'-c','copy',str(out_path)])
        concat_list.unlink(missing_ok=True)

    def composite(base_path, overlays, subtitles_path, out_path, edit_dir):
        if not overlays and subtitles_path is None:
            return module.run(['ffmpeg','-hide_banner','-loglevel','warning','-y','-i',str(base_path),
                               '-c','copy',str(out_path)])
        inputs = ['-i', str(base_path)]
        filters = []
        current = '[0:v]'
        for i,ov in enumerate(overlays,1):
            inputs += ['-i',str(module.resolve_path(ov['file'],edit_dir))]
            start = float(ov['start_in_output'])
            end = start + float(ov['duration'])
            filters.append(f'[{i}:v]setpts=PTS-STARTPTS+{start}/TB[a{i}]')
            next_label = f'[v{i}]'
            filters.append(f"{current}[a{i}]overlay=eof_action=pass:repeatlast=0:enable='gte(t,{start})*lt(t,{end})'{next_label}")
            current = next_label
        if subtitles_path is not None:
            subs = subtitles_path.resolve().as_posix().replace(':',r'\:').replace("'",r"\'")
            style = 'FontName=Microsoft YaHei,FontSize=22,PrimaryColour=&H00FFFFFF,OutlineColour=&H00101419,BorderStyle=1,Outline=2,Shadow=0,Alignment=2,MarginV=25'
            filters.append(f"{current}subtitles=filename='{subs}':force_style='{style}'[outv]")
        else:
            filters.append(f'{current}null[outv]')
        graph = ';'.join(filters)
        # Keep the actual filter graph as acceptance evidence.
        (edit_dir / 'composite-filter.txt').write_text(graph, encoding='utf-8')
        print(f'video-use composite: {len(overlays)} overlays, subtitles last={subtitles_path is not None}',flush=True)
        module.run(['ffmpeg','-hide_banner','-loglevel','warning','-y',*inputs,'-filter_complex',graph,
                    '-map','[outv]','-map','0:a?','-c:v','libx264','-preset','fast','-crf','18',
                    '-pix_fmt','yuv420p','-c:a','copy',str(out_path)])

    module.concat_segments = concat_segments
    module.build_final_composite = composite
    return module


def video_use_worker(args):
    # Runs in its own Python process, so PATH is never changed for the user.
    os.environ.update(environment())
    module = load_video_use()
    edl_path=Path(args.edl).resolve()
    edl=json.loads(edl_path.read_text(encoding='utf-8-sig'))
    edit_dir=edl_path.parent
    target=Path(args.output).resolve()
    # AAC has encoder priming/padding per independently encoded segment. Stream-
    # copying those packets at arbitrary cuts causes overlapping DTS. Keep PCM
    # through the lossless intermediate concat and encode AAC only at the end.
    first=module.resolve_path(edl['sources'][edl['ranges'][0]['source']],edit_dir)
    rate=module.parse_fps(args.fps) if args.fps else (module.probe_source_fps(first) or '30')
    requested_canvas=edl.get('canvas')
    if requested_canvas is not None and requested_canvas not in ([1920,1080],[1080,1920]):
        raise ValueError('EDL canvas must be 1080p landscape or portrait')
    portrait=requested_canvas == [1080,1920] if requested_canvas else module.is_portrait_source(first)
    canvas=(720,1280) if args.draft and portrait else ((1280,720) if args.draft else ((1080,1920) if portrait else (1920,1080)))
    grade=module.resolve_grade_filter(edl.get('grade'))
    clips_dir=edit_dir/'clips_pcm'
    clips_dir.mkdir(exist_ok=True)
    segments=[]
    source_hashes={}
    entry_hash=hashlib.sha256(Path(__file__).read_bytes()).hexdigest() if edl.get('cache_segments') else None
    for i,r in enumerate(edl['ranges']):
        source=module.resolve_path(edl['sources'][r['source']],edit_dir)
        start=float(r['start']);duration=float(r['end'])-start
        probe=subprocess.run([str(FFMPEG/'ffprobe.exe'),'-v','error','-show_streams','-show_format','-of','json',str(source)],capture_output=True,check=True,text=True)
        info=json.loads(probe.stdout)
        if float(r['end']) > float(info['format']['duration']) + .04:
            raise ValueError(f'Cut exceeds source duration: {source.name}')
        has_audio=any(s['codec_type']=='audio' for s in info['streams'])
        vf=[]
        if module.is_hdr_source(source):
            vf.append(module.TONEMAP_CHAIN)
        width,height=canvas
        vf += [f'scale={width}:{height}:force_original_aspect_ratio=decrease',f'pad={width}:{height}:(ow-iw)/2:(oh-ih)/2', 'setsar=1']
        this_grade=module.auto_grade_for_clip(source,start=start,duration=duration,verbose=False)[0] if grade=='__AUTO__' else grade
        if this_grade:
            vf.append(this_grade)
        path=clips_dir/f'seg_{i:02d}_{r["source"]}.mkv'
        # Optional project-local content cache; unchanged sources/cuts are reused.
        # The ordinary entry keeps its previous behavior unless the EDL opts in.
        if edl.get('cache_segments'):
            source_key=source.resolve()
            if source_key not in source_hashes:
                source_hash = hashlib.sha256()
                with source.open('rb') as source_stream:
                    for block in iter(lambda: source_stream.read(1024*1024), b''):
                        source_hash.update(block)
                source_hashes[source_key]=source_hash.hexdigest()
            recipe = {'source':source_hashes[source_key],'start':start,'duration':duration,
                      'canvas':canvas,'fps':rate,'filters':vf,'draft':args.draft,
                      'entry':entry_hash}
            digest = hashlib.sha256(json.dumps(recipe,sort_keys=True).encode()).hexdigest()
            path = clips_dir/f'{digest}.mkv'
            if path.is_file():
                print(f'video-use cache hit: {r["source"]}',flush=True)
                segments.append(path)
                continue
        inputs=['-ss',str(start),'-i',str(source)]
        if not has_audio:
            inputs += ['-f','lavfi','-i','anullsrc=r=48000:cl=stereo']
        audio_map='0:a:0' if has_audio else '1:a:0'
        fade=f'afade=t=in:st=0:d=0.03,afade=t=out:st={max(0,duration-.03):.6f}:d=0.03'
        print(f'video-use extraction: {r["source"]} {start:.3f}–{start+duration:.3f}s; PCM intermediate',flush=True)
        pending = path.with_name(path.stem+'.partial.mkv')
        module.run(['ffmpeg','-hide_banner','-loglevel','warning','-y',*inputs,'-t',str(duration),
                    '-map','0:v:0','-map',audio_map,'-vf',','.join(vf),'-af',fade,
                    '-c:v','libx264','-preset','ultrafast' if args.draft else 'fast','-crf','28' if args.draft else '20',
                    '-pix_fmt','yuv420p','-r',rate,'-c:a','pcm_s16le','-ar','48000','-ac','2',str(pending)])
        pending.replace(path)
        segments.append(path)
    base=edit_dir/'base-pcm.mkv'
    module.concat_segments(segments,base,edit_dir)
    subtitles=None
    if args.build_subtitles:
        subtitles=edit_dir/'master.srt'
        module.build_master_srt(edl,edit_dir,subtitles)
    elif edl.get('subtitles'):
        subtitles=module.resolve_subtitles_path(edl['subtitles'],edit_dir)
    composite_path=edit_dir/'composite-pcm.mkv'
    module.build_final_composite(base,edl.get('overlays') or [],subtitles,composite_path,edit_dir)
    # The existing video-use two-pass loudness helper performs the one final
    # AAC encoding; video is stream-copied here.
    if args.draft:
        module.apply_loudnorm_two_pass(composite_path,target,preview=True)
    else:
        measurement=module.measure_loudness(composite_path)
        if measurement and not math.isfinite(float(measurement['input_i'])):
            print('Silent audio: preserve silence; loudness normalization is not applicable',flush=True)
            module.run(['ffmpeg','-hide_banner','-loglevel','warning','-y','-i',str(composite_path),
                        '-c:v','copy','-c:a','aac','-ar','48000','-b:a','192k','-movflags','+faststart',str(target)])
        else:
            # Reuse the already completed measurement for the upstream second pass.
            module.measure_loudness=lambda _: measurement
            module.apply_loudnorm_two_pass(composite_path,target,preview=False)


def main():
    if hasattr(sys.stdout,'reconfigure'):
        sys.stdout.reconfigure(encoding='utf-8')
    if sys.argv[1:2] == ['manim']:
        return invoke([PYTHON,CODEX_DIR/'runtimes/personal-video/run_manim.py',*sys.argv[2:]])
    if sys.argv[1:2] == ['blender']:
        return subprocess.run([str(PYTHON),'-X','utf8',str(ROOT/'blender_tools.py'),*sys.argv[2:]],
                              env=environment()).returncode
    p = argparse.ArgumentParser(description='Remotion + video-use local entry; no cloud calls')
    commands = p.add_subparsers(dest='command',required=True)
    commands.add_parser('doctor')
    commands.add_parser('manim',help='Pass arguments to the shared Manim CLI')
    commands.add_parser('blender',help='Blender start, status, render and verify; use blender --help')
    production=commands.add_parser('production')
    production.add_argument('timeline')
    production.add_argument('output',nargs='?')
    production.add_argument('--validate',action='store_true')
    compositions = commands.add_parser('compositions')
    studio = commands.add_parser('studio')
    studio.add_argument('--port',type=int,default=3100)
    render = commands.add_parser('remotion-render')
    render.add_argument('composition')
    render.add_argument('output')
    render.add_argument('--transparent',action='store_true')
    for name in ('video-use','_video-use-worker'):
        edit = commands.add_parser(name)
        edit.add_argument('edl')
        edit.add_argument('output')
        edit.add_argument('--fps')
        edit.add_argument('--draft',action='store_true')
        edit.add_argument('--build-subtitles',action='store_true')
    view = commands.add_parser('timeline')
    view.add_argument('video')
    view.add_argument('start',type=float)
    view.add_argument('end',type=float)
    view.add_argument('output')
    args=p.parse_args()
    if args.command=='doctor':
        return doctor()
    if args.command=='production':
        argv=[PYTHON,'-X','utf8',ROOT/'production_runner.py',Path(args.timeline).resolve()]
        if args.validate:
            argv.append('--validate')
        elif args.output:
            argv.append(Path(args.output).resolve())
        else:
            p.error('production requires output or --validate')
        return invoke(argv)
    if args.command=='compositions':
        return invoke([*remotion_cli(),'compositions','src/index.tsx',f'--browser-executable={remotion_browser()}'],REMOTION)
    if args.command=='studio':
        return invoke([*remotion_cli(),'studio','src/index.tsx','--no-open',f'--port={args.port}'],REMOTION)
    if args.command=='remotion-render':
        target=Path(args.output).resolve()
        if target.exists():
            p.error('Output exists; use a new version filename')
        target.parent.mkdir(parents=True,exist_ok=True)
        flags = ['--codec=prores','--prores-profile=4444','--pixel-format=yuva444p10le','--image-format=png'] if args.transparent else ['--codec=h264','--pixel-format=yuv420p','--crf=18']
        return invoke([*remotion_cli(),'render','src/index.tsx',args.composition,target,
                       f'--browser-executable={remotion_browser()}','--concurrency=2','--overwrite=false',*flags],REMOTION)
    if args.command=='_video-use-worker':
        return video_use_worker(args)
    if args.command=='video-use':
        target=Path(args.output).resolve()
        if target.exists():
            p.error('Output exists; use a new version filename')
        edl_path=Path(args.edl).resolve()
        data=json.loads(edl_path.read_text(encoding='utf-8-sig'))
        ranges=data.get('ranges',[])
        if not ranges:
            p.error('EDL must contain at least one range')
        for r in ranges:
            if not 0 <= float(r['start']) < float(r['end']):
                p.error('Invalid EDL cut interval')
        worker=['-X','utf8',str(Path(__file__).resolve()),'_video-use-worker',str(edl_path),str(target)]
        for flag in ('draft','build_subtitles'):
            if getattr(args,flag):
                worker.append('--'+flag.replace('_','-'))
        if args.fps:
            worker += ['--fps',args.fps]
        return invoke([PYTHON,*worker])
    if args.command=='timeline':
        return invoke([PYTHON,'-X','utf8',HELPERS/'timeline_view.py',Path(args.video).resolve(),
                       args.start,args.end,'-o',Path(args.output).resolve(),'--n-frames','6'])


if __name__=='__main__':
    sys.exit(main() or 0)
