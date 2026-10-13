"""Talking-head workflow: reuse deployed Doubao/visual jobs and local video-use.

Only advance --allow-paid-calls can upload or contact a cloud service.
Semantic take selection belongs to Codex; this entry executes an explicit plan.
"""
from __future__ import annotations

import argparse
import asyncio
import copy
import hashlib
import importlib
import importlib.util
import json
import math
import os
from pathlib import Path
import re
import site
import subprocess
import sys
import unicodedata

CODEX = Path(os.environ.get('CODEX_HOME') or Path.home()/'.codex')
RUNTIME = CODEX/'runtimes/personal-video'
SESSION = 'talking-head.json'
NATIVE_ASR = {'doubao2', 'doubao_turbo'}


def sha(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def number(value):
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        raise ValueError('Expected a finite timestamp or numeric setting')
    return float(value)


def safe(path, boundary):
    path, boundary = Path(path).absolute(), Path(boundary).absolute()
    if not path.resolve().is_relative_to(boundary.resolve()):
        raise ValueError('Output escapes the edit directory')
    for item in (path, *path.parents):
        if item.is_symlink() or item.is_junction():
            raise ValueError('Linked output directory or file')
        if item == boundary:
            break
    return path


def read_json(path):
    return json.loads(Path(path).read_text(encoding='utf-8-sig'))


def json_bytes(value):
    return (json.dumps(value, ensure_ascii=False, indent=2)+'\n').encode('utf-8')


def atomic(path, content):
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_name(path.name+'.talking-head.tmp')
    if temp.exists():
        raise ValueError('An interrupted write exists; inspect it before resuming')
    with temp.open('xb') as stream:
        stream.write(content)
    temp.replace(path)


def owned(edit, state, relative, content):
    target = safe(edit/relative, edit)
    expected = hashlib.sha256(content).hexdigest()
    prior = state.setdefault('generated_files_sha256', {}).get(relative)
    if target.exists() and sha(target) not in (prior, expected):
        raise ValueError('Generated file has independent edits; preserve it before regenerating: '+relative)
    if not target.exists() or sha(target) != expected:
        atomic(target, content)
    state['generated_files_sha256'][relative] = expected


def save_session(edit, state):
    atomic(safe(edit/SESSION, edit), json_bytes(state))


def load_session(edit, verify_sources=True):
    state = read_json(safe(edit/SESSION, edit))
    if state.get('schema_version') != 1 or not state.get('assets'):
        raise ValueError('Unknown or empty talking-head session')
    if verify_sources:
        for asset in state['assets']:
            if sha(asset['source']) != asset['sha256']:
                raise ValueError('Source changed; existing transcription and plan cannot be reused')
    return state


def backend():
    if not (RUNTIME/'api/workflow.py').is_file():
        raise ValueError('Shared personal-video runtime is unavailable; locate its maintenance entry')
    site.addsitedir(str(RUNTIME/'python-packages'))
    sys.path.insert(0, str(RUNTIME/'api'))
    os.environ.setdefault('VOLC_FFMPEG', str(RUNTIME/'native/ffmpeg/ffmpeg.exe'))
    os.environ.setdefault('VOLC_FFPROBE', str(RUNTIME/'native/ffmpeg/ffprobe.exe'))
    configuration = RUNTIME/'runtime-config.json'
    if configuration.is_file() and read_json(configuration).get('legacy_outputs'):
        os.environ.setdefault('VOLC_LEGACY_OUTPUTS', read_json(configuration)['legacy_outputs'])
    return importlib.import_module('workflow')


def asset_record(asset):
    metadata = asset['metadata']
    video = next((s for s in metadata['streams'] if s.get('codec_type') == 'video'), {})
    audio_count = sum(s.get('codec_type') == 'audio' for s in metadata['streams'])
    rate = video.get('avg_frame_rate') or video.get('r_frame_rate') or '30/1'
    try:
        a, b = rate.split('/')
        fps = float(a)/float(b)
        if not math.isfinite(fps) or fps <= 0:
            raise ValueError()
    except (ValueError, ZeroDivisionError):
        fps = 30.0
    width, height = video.get('width', 1920), video.get('height', 1080)
    rotation = next((s.get('rotation', 0) for s in video.get('side_data_list', []) if 'rotation' in s), 0)
    if abs(float(rotation)) % 180 == 90:
        width, height = height, width
    return {'id': asset['id'], 'source': str(Path(asset['source']).resolve()),
            'sha256': asset['sha256'], 'duration': metadata['duration'],
            'width': width, 'height': height, 'fps': fps, 'audio_streams': audio_count}


def new_state(job_id, folder, job):
    return {'schema_version': 1, 'job_id': job_id, 'job_folder': str(folder),
            'mode': job['task'], 'provider': job.get('asr_backend'),
            'assets': [asset_record(a) for a in job['assets']], 'state': job['state'],
            'generated_files_sha256': {}, 'caption_review_required': True}


def reuse_asr(workflow, new_id, old_id):
    old_folder, old = workflow.load(old_id)
    new_folder, new = workflow.load(new_id)
    if old['state'] != 'completed' or old.get('asr_backend') not in NATIVE_ASR:
        raise ValueError('Only a completed native Doubao job is eligible for ASR reuse')
    if old['asr_backend'] != new.get('asr_backend'):
        raise ValueError('Select the cached ASR backend when reusing evidence; do not relabel its source')
    if not set(new.get('asr_features', [])) <= set(old.get('asr_features', [])) or (new.get('speaker_info') and not old.get('speaker_info')):
        raise ValueError('Cached ASR did not request these features; no silent coverage upgrade')
    lookup = {}
    for clip in old['clips']:
        asset = next(a for a in old['assets'] if a['id'] == clip['asset_id'])
        if clip['asr']['state'] == 'done':
            lookup[(asset['sha256'], clip['start'], clip['duration'], clip.get('audio_sha256'))] = clip
    replacements = []
    for clip in new['clips']:
        if clip['asr']['state'] == 'skip':
            continue
        asset = next(a for a in new['assets'] if a['id'] == clip['asset_id'])
        key = (asset['sha256'], clip['start'], clip['duration'], clip.get('audio_sha256'))
        if key not in lookup:
            raise ValueError('Cached ASR source or chunk boundaries differ; no paid calls have been made')
        original = lookup[key]
        segments = copy.deepcopy(original['asr']['segments'])
        for segment in segments:
            segment['asset_id'], segment['clip_id'] = clip['asset_id'], clip['id']
        replacements.append((clip, {'state': 'done', 'segments': segments,
                                    'reused_from_job': old_id, 'reused_from_clip': original['id']}))
    for clip, cached in replacements:
        clip['asr'] = cached
    audio_calls = 1 if new.get('asr_transport') == 'inline' else 2
    new['planned_paid_requests'] = sum((c['asr']['state'] not in ('skip', 'done'))*audio_calls +
                                      (c['visual']['state'] not in ('skip', 'done')) for c in new['clips'])
    workflow.dump(new_folder/'job.json', new)


def prepare(edit, sources, mode='video_analysis', profile='standard', clip_seconds=120,
            visual_fps=1.0, reuse_job=None, asr_backend_name='doubao_turbo', asr_features=None, speaker_info=False):
    if asr_backend_name not in NATIVE_ASR:
        raise ValueError('Choose doubao2 or doubao_turbo for word-level editing evidence')
    options = {'profile': profile, 'clip_seconds': clip_seconds, 'visual_fps': visual_fps}
    if asr_features: options['asr_features'] = sorted(set(asr_features))
    if speaker_info: options['speaker_info'] = True
    if (edit/SESSION).exists():
        state = load_session(edit)
        wanted = [str(Path(p).resolve()) for p in sources]
        if wanted != [a['source'] for a in state['assets']] or mode != state['mode']:
            raise ValueError('This edit directory belongs to another source selection or mode')
        if mode != 'cuts_only' and state.get('prepare_options') != options:
            raise ValueError('Prepared options changed; retain the original job and choose a new edit directory')
        if mode != 'cuts_only' and state.get('provider') != asr_backend_name:
            raise ValueError('Prepared ASR backend changed; retain the original job')
        return {'state': state['state'], 'job_id': state['job_id'], 'cached': True}
    safe(edit, edit)
    workflow = backend()
    if mode == 'cuts_only':
        assets = []
        for i, source in enumerate(sources):
            source = Path(source).resolve()
            metadata = workflow.probe(source)
            if not metadata['has_video']:
                raise ValueError('Talking-head source must contain video')
            assets.append({'id': f'video_{i+1:03d}', 'source': str(source),
                           'sha256': sha(source), 'metadata': metadata})
        state = {'schema_version': 1, 'job_id': None, 'mode': mode, 'provider': None,
                 'assets': [asset_record(a) for a in assets], 'state': 'local_ready',
                 'generated_files_sha256': {}, 'caption_review_required': False}
    else:
        for source in sources:
            if not workflow.probe(Path(source).resolve())['has_video']:
                raise ValueError('Talking-head editing needs a video source')
        result = workflow.prepare([str(Path(p).resolve()) for p in sources], task=mode,
                                  profile=profile, clip_seconds=clip_seconds, fps=visual_fps,
                                  max_frames=min(600, math.ceil(clip_seconds*visual_fps)),
                                  speaker_info=speaker_info, asr_backend_name=asr_backend_name,
                                  asr_features=asr_features)
        folder, job = workflow.load(result['job_id'])
        state = new_state(result['job_id'], folder, job)
        state['prepare_options'] = options
        save_session(edit, state)
        if reuse_job:
            try:
                reuse_asr(workflow, result['job_id'], reuse_job)
            except Exception:
                state['state'] = 'needs_review'
                state['reuse_failed'] = True
                save_session(edit, state)
                raise
        folder, job = workflow.load(result['job_id'])
        state['planned_paid_requests'] = job['planned_paid_requests']
    save_session(edit, state)
    return status(edit)


def join_text(items):
    result = ''
    for text in items:
        text = text.strip()
        if not text:
            continue
        if result and re.search(r'[A-Za-z0-9]$', result) and re.match(r'[A-Za-z0-9]', text):
            result += ' '
        result += text
    return result


def punctuation_only(text):
    return all(c.isspace() or unicodedata.category(c).startswith('P') for c in text)


def normalize(segments, asset, provider='doubao2'):
    if not isinstance(segments, list):
        raise ValueError('Expected the existing workflow sentence array, not an unparsed API response')
    words, rows, unaligned = [], [], 0
    previous = -1.0
    for segment in segments:
        start, end = number(segment['start']), number(segment['end'])
        text = segment.get('text')
        if not isinstance(text, str) or not 0 <= start <= end <= asset['duration']+.001:
            raise ValueError('Invalid sentence or source timestamps')
        tokens = segment.get('words')
        if not isinstance(tokens, list) or (text.strip() and not tokens):
            raise ValueError('Word timestamps are required; phrase-only results cannot guide precise speech cuts')
        first = len(words)
        cursor, aligned = 0, True
        for token in tokens:
            a, b, raw = number(token['start']), number(token['end']), token.get('text')
            if not isinstance(raw, str) or not raw.strip() or not start-.001 <= a < b <= end+.001 or a < previous:
                raise ValueError('Invalid, unsorted or missing word timestamps')
            if words and a < words[-1]['end']-.001:
                raise ValueError('Overlapping words require review before caption timing')
            previous = a
            raw = raw.strip()
            position = text.find(raw, cursor)
            if position < cursor or not punctuation_only(text[cursor:position]):
                aligned = False
            display = raw
            if position >= cursor:
                cursor = position+len(raw)
                while cursor < len(text) and unicodedata.category(text[cursor]).startswith('P'):
                    display += text[cursor]
                    cursor += 1
            word = {'start': a, 'end': b, 'text': raw, 'display_text': display, 'type': 'word'}
            if segment.get('speaker') is not None:
                word['speaker_id'] = str(segment['speaker'])
            words.append(word)
        if not punctuation_only(text[cursor:]):
            aligned = False
        if not aligned:
            unaligned += 1
            for word in words[first:]:
                word['display_text'] = word['text']
        rows.append({'start': start, 'end': end, 'text': text,
                     'word_start': first, 'word_end': len(words), 'clip_id': segment.get('clip_id'),
                     'additions': copy.deepcopy(segment.get('additions', {}))})
    return {'schema_version': 1, 'provider': provider, 'source_sha256': asset['sha256'],
            'time_base': 'original_source_seconds', 'text': ''.join(s['text'] for s in rows),
            'words': words, 'segments': rows, 'punctuation_alignment_issues': unaligned}


def sync(edit):
    state = load_session(edit)
    if state['mode'] == 'cuts_only':
        return {'state': 'local_ready', 'job_id': None, 'cloud_calls': 0}
    workflow = backend()
    folder, job = workflow.load(state['job_id'])
    if job['state'] != 'completed' or job.get('asr_backend') not in NATIVE_ASR:
        raise ValueError('Import requires a completed native Doubao workflow; resume the original job')
    if [asset_record(a) for a in job['assets']] != state['assets']:
        raise ValueError('Saved job source selection differs from the edit session')
    packed, outputs = [], []
    for asset in state['assets']:
        raw = folder/asset['id']/'transcript.json'
        transcript = normalize(read_json(raw), asset, job['asr_backend'])
        transcript['raw_transcript_path'] = str(raw)
        transcript['raw_transcript_sha256'] = sha(raw)
        path = f"transcripts/{asset['id']}.json"
        owned(edit, state, path, json_bytes(transcript))
        outputs.append(str(edit/path))
        packed.append('## '+asset['id']+' — '+Path(asset['source']).name)
        for sentence in transcript['segments']:
            packed.append(f"[{sentence['start']:.3f}–{sentence['end']:.3f}] {sentence['text']} (words {sentence['word_start']}:{sentence['word_end']})")
        packed.append('')
    owned(edit, state, 'takes_packed.md', ('\n'.join(packed)+'\n').encode('utf-8'))
    evidence = folder/'video_analysis.json'
    if evidence.is_file():
        owned(edit, state, 'analysis/video_analysis.json', evidence.read_bytes())
    videos = read_json(evidence).get('videos', []) if evidence.is_file() else []
    state['audio_understanding'] = {a['id']: next((v.get('audio_understanding', 'not_analyzed')
        for v in videos if v['asset_id'] == a['id']), 'no_audio_track' if not a['audio_streams'] else 'not_analyzed') for a in state['assets']}
    state['asr_feature_coverage'] = {v['asset_id']: v.get('asr_feature_coverage', {}) for v in videos}
    state['state'] = 'analysis_ready'
    state['visual_analysis_completed'] = any(c['visual']['state'] == 'done' for c in job['clips'])
    save_session(edit, state)
    return {'state': state['state'], 'transcripts': outputs,
            'visual_analysis_completed': state['visual_analysis_completed'],
            'audio_understanding': state['audio_understanding'], 'asr_feature_coverage': state['asr_feature_coverage'], 'cloud_calls': 0}


def import_job(edit, job_id):
    if (edit/SESSION).exists():
        state = load_session(edit)
        if state.get('job_id') != job_id:
            raise ValueError('Do not replace the existing edit session with another cloud job')
    else:
        workflow = backend()
        folder, job = workflow.load(job_id)
        if job['state'] != 'completed' or job.get('asr_backend') not in NATIVE_ASR:
            raise ValueError('Only completed native Doubao jobs can be imported')
        state = new_state(job_id, folder, job)
        for asset in state['assets']:
            if sha(asset['source']) != asset['sha256']:
                raise ValueError('Cached recognition belongs to a changed source')
        save_session(edit, state)
    return sync(edit)


def status(edit):
    state = load_session(edit)
    report = {'state': state['state'], 'mode': state['mode'], 'job_id': state['job_id'],
              'sources': [{'id': a['id'], 'source': a['source'], 'audio_streams': a['audio_streams']} for a in state['assets']],
              'audio_understanding': state.get('audio_understanding', {}), 'asr_feature_coverage': state.get('asr_feature_coverage', {})}
    if state['job_id']:
        folder, job = backend().load(state['job_id'])
        report.update(cloud_state=job['state'], planned_paid_requests=job['planned_paid_requests'],
                      paid_requests_attempted=job.get('paid_requests_attempted', 0), job_folder=str(folder))
    return report


def advance(edit, allow_paid_calls=False):
    state = load_session(edit)
    if not state['job_id'] or state.get('reuse_failed'):
        raise ValueError('No eligible cloud job; review this session instead of submitting another task')
    workflow = backend()
    report = asyncio.run(workflow.advance(state['job_id'], allow_paid_calls=allow_paid_calls))
    state['cloud_state'] = report['state']
    save_session(edit, state)
    if report['state'] == 'completed':
        return sync(edit)
    return {k: report[k] for k in ('job_id', 'state', 'planned_paid_requests', 'paid_requests_attempted',
                                 'action_required', 'busy') if k in report}


def default_groups(words, indices, max_chars=16):
    groups, current = [], []
    for index in indices:
        word = words[index]
        if current and (word['start']-words[current[-1]]['end'] >= .5 or
                        len(join_text(words[i]['display_text'] for i in current+[index])) > max_chars):
            groups.append(current)
            current = []
        current.append(index)
        if word['display_text'].endswith(('。', '！', '？', '，', '；', '!', '?', ';')):
            groups.append(current)
            current = []
    if current:
        groups.append(current)
    return groups


def stamp(seconds):
    milliseconds = round(seconds*1000)
    h, rem = divmod(milliseconds, 3600000)
    m, rem = divmod(rem, 60000)
    s, ms = divmod(rem, 1000)
    return f'{h:02}:{m:02}:{s:02},{ms:03}'


def ass_captions(captions, width, height):
    def time(seconds):
        ticks = round(seconds*100)
        h, rem = divmod(ticks, 360000)
        m, rem = divmod(rem, 6000)
        s, cs = divmod(rem, 100)
        return f'{h}:{m:02}:{s:02}.{cs:02}'

    header = (f'[Script Info]\nScriptType: v4.00+\nPlayResX: {width}\nPlayResY: {height}\n'
              'ScaledBorderAndShadow: yes\n\n[V4+ Styles]\n'
              'Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, '
              'Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, '
              'Alignment, MarginL, MarginR, MarginV, Encoding\n'
              'Style: Default,Microsoft YaHei,48,&H00FFFFFF,&H000000FF,&H00101419,&H80000000,'
              '0,0,0,0,100,100,0,0,1,2,0,2,40,40,60,1\n\n[Events]\n'
              'Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text\n')
    lines = []
    for a, b, text in captions:
        escaped = text.replace('\\', '\\\\').replace('{', r'\{').replace('}', r'\}').replace('\n', r'\N')
        lines.append(f'Dialogue: 0,{time(a)},{time(b)},Default,,0,0,0,,{escaped}')
    return (header+'\n'.join(lines)+'\n').encode('utf-8')


def build_plan(edit, plan_path):
    state = load_session(edit)
    plan = read_json(plan_path)
    if not isinstance(plan, dict) or not isinstance(plan.get('ranges'), list):
        raise ValueError('A plan must contain a ranges array')
    if set(plan)-{'ranges', 'fps', 'caption_groups', 'word_corrections', 'subtitle_style', 'grade', 'overlays', 'max_caption_chars'}:
        raise ValueError('Unknown plan field; do not silently ignore editing instructions')
    assets = {a['id']: a for a in state['assets']}
    fps = number(plan.get('fps', state['assets'][0]['fps']))
    if not 1 <= fps <= 120:
        raise ValueError('Choose an explicit supported output frame rate')
    ranges, transcript_cache, captions, offsets = [], {}, [], 0.0
    all_manual = plan.get('caption_groups', {})
    if not isinstance(all_manual, dict) or set(all_manual)-set(assets):
        raise ValueError('Caption groups must refer to known source IDs')
    corrections = plan.get('word_corrections', {})
    if (not isinstance(corrections, dict) or set(corrections)-set(assets)
            or any(not isinstance(v, dict) for v in corrections.values())):
        raise ValueError('Word corrections must refer to known source IDs')
    if not isinstance(plan.get('overlays', []), list):
        raise ValueError('Overlays must be an array')
    for row in plan.get('ranges', []):
        if not isinstance(row, dict) or set(row) != {'source', 'start', 'end'} or row['source'] not in assets:
            raise ValueError('Ranges need a known source, start and end')
        asset = assets[row['source']]
        start, end = number(row['start']), number(row['end'])
        if not 0 <= start < end <= asset['duration']+.000001:
            raise ValueError('Cut interval is outside the source')
        if any(abs(t*fps-round(t*fps)) > .001 for t in (start, end)):
            raise ValueError('Choose cut edges on output frame boundaries, with room around spoken words')
        start, end = round(start*fps)/fps, round(end*fps)/fps
        ranges.append({'source': row['source'], 'start': start, 'end': end})
        tr = edit/'transcripts'/f"{row['source']}.json"
        if tr.is_file():
            relative = tr.relative_to(edit).as_posix()
            if sha(tr) != state['generated_files_sha256'].get(relative):
                raise ValueError('Transcription changed independently; review before selecting cuts')
            transcript = transcript_cache.setdefault(row['source'], read_json(tr))
            words = copy.deepcopy(transcript['words'])
            for key, text in corrections.get(row['source'], {}).items():
                if not isinstance(key, str) or not key.isdecimal() or not 0 <= int(key) < len(words):
                    raise ValueError('Word correction index is outside the transcription')
                if not isinstance(text, str) or not text.strip() or '\n' in text:
                    raise ValueError('Word correction must be nonempty display text without changing timestamps')
                words[int(key)]['display_text'] = text
            inside = []
            for index, word in enumerate(words):
                a, b = word['start'], word['end']
                if max(a, start) < min(b, end)-.000001:
                    if a < start-.000001 or b > end+.000001:
                        raise ValueError('Cut would split a recognized word; adjust the edge and inspect the original sound')
                    inside.append(index)
            if row['source'] in all_manual:
                groups = []
                pairs = all_manual[row['source']]
                if not isinstance(pairs, list):
                    raise ValueError('Caption groups must be an array of word index pairs')
                previous_end = 0
                for pair in pairs:
                    if not isinstance(pair, list) or len(pair) != 2 or any(type(i) is not int for i in pair):
                        raise ValueError('Caption groups use [start_word, end_word_exclusive]')
                    a, b = pair
                    if not previous_end <= a < b <= len(words):
                        raise ValueError('Caption word group is outside the transcription')
                    previous_end = b
                    group = [i for i in inside if a <= i < b]
                    if group:
                        groups.append(group)
                if [i for group in groups for i in group] != inside:
                    raise ValueError('Caption groups must preserve each retained word once and in order')
            else:
                limit = plan.get('max_caption_chars', 16)
                if type(limit) is not int or not 4 <= limit <= 50:
                    raise ValueError('Caption character limit must be between 4 and 50')
                groups = default_groups(words, inside, limit)
            for group in groups:
                captions.append((offsets+words[group[0]]['start']-start,
                                 offsets+words[group[-1]]['end']-start,
                                 join_text(words[i]['display_text'] for i in group)))
        elif state['mode'] != 'cuts_only':
            raise ValueError('Complete or import recognition before speech-based selection')
        offsets += end-start
    if not ranges:
        raise ValueError('A plan needs at least one explicit keep interval')
    for overlay in plan.get('overlays', []):
        if not isinstance(overlay, dict) or set(overlay) != {'file', 'start_in_output', 'duration'}:
            raise ValueError('This overlay adapter supports only file, start_in_output and duration')
        if not (edit/overlay['file']).is_file():
            raise ValueError('Overlay file is missing')
        start, duration = number(overlay['start_in_output']), number(overlay['duration'])
        if start < 0 or duration <= 0 or start+duration > offsets+.001:
            raise ValueError('Overlay exceeds the output timeline')
    first = assets[ranges[0]['source']]
    portrait = first['height'] > first['width']
    width, height = (1080, 1920) if portrait else (1920, 1080)
    font_size = round(min(height*.045, width/22))
    style = plan.get('subtitle_style', f'FontName=Microsoft YaHei,FontSize={font_size},PrimaryColour=&H00FFFFFF,OutlineColour=&H00101419,BorderStyle=1,Outline=2,Shadow=0,Alignment=2,MarginV={round(height*.06)}')
    if not isinstance(style, str) or not style.strip():
        raise ValueError('Subtitle style must be a nonempty string')
    if not all(re.fullmatch(r"[A-Za-z][A-Za-z0-9]*=[^'\r\n;\\\[\]]+", p) for p in style.split(',')):
        raise ValueError('Subtitle style must use ordinary ASS key=value fields')
    srt = '\n\n'.join(f'{i}\n{stamp(a)} --> {stamp(b)}\n{text}' for i, (a,b,text) in enumerate(captions,1))+'\n'
    edl = {'version': 1, 'sources': {name: a['source'] for name,a in assets.items()},
           'ranges': ranges, 'grade': plan.get('grade'), 'overlays': plan.get('overlays', []),
           'total_duration_s': offsets}
    edl['overlays'] = [dict(o, file=str((edit/o['file']).resolve())) for o in edl['overlays']]
    if captions:
        owned(edit, state, 'master.srt', srt.encode('utf-8'))
        owned(edit, state, 'master.ass', ass_captions(captions, width, height))
        edl['subtitles'] = str(edit/'master.ass')
    owned(edit, state, 'edl.json', json_bytes(edl))
    owned(edit, state, 'editing-plan.json', json_bytes(plan))
    state.update(state='planned', output_fps=fps, caption_review_required=bool(captions),
                 expected_duration_s=offsets, caption_cues=len(captions),
                 caption_style=style, output_canvas=[width, height])
    save_session(edit, state)
    return {'state': 'planned', 'edl': str(edit/'edl.json'), 'caption_cues': len(captions),
            'expected_duration_s': offsets, 'caption_review_required': bool(captions), 'cloud_calls': 0}


def render(edit, output, preview=False):
    state = load_session(edit)
    if state['state'] not in ('planned', 'rendered'):
        raise ValueError('Create an explicit editing plan before rendering')
    output = safe(output, edit)
    if output.exists():
        raise ValueError('Output already exists; use a new version filename')
    work = safe(edit/'render-work'/output.name, edit)
    if work.exists():
        raise ValueError('A render attempt already exists for this filename; inspect it and use a new version')
    edl_path = edit/'edl.json'
    for name in ('edl.json', 'master.srt', 'master.ass'):
        if name in state['generated_files_sha256'] and sha(edit/name) != state['generated_files_sha256'][name]:
            raise ValueError('Plan or captions changed independently; regenerate from the reviewed plan')
    work.mkdir(parents=True)
    atomic(work/'edl.json', edl_path.read_bytes())
    flags = ['--fps', str(state['output_fps']), '--caption-style', state['caption_style']]
    if preview:
        flags.append('--draft')
    result = subprocess.run([sys.executable, '-B', '-X', 'utf8', str(Path(__file__).resolve()),
                             '_render-worker', str(work/'edl.json'), str(output), *flags],
                            capture_output=True, text=True, encoding='utf-8', errors='replace',
                            creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
    log = 'render-'+output.stem+'.log'
    owned(edit, state, log, (result.stdout+result.stderr).encode('utf-8'))
    if result.returncode:
        save_session(edit, state)
        raise ValueError('Local render failed; inspect '+str(edit/log))
    state.update(state='rendered', last_output=str(output), last_output_sha256=sha(output),
                 output_review_required=True)
    save_session(edit, state)
    return {'state': 'rendered', 'output': str(output), 'output_review_required': True, 'cloud_calls': 0}


def render_worker(args):
    """Reuse shared cutting/PCM concat/loudness; adapt only caption composition.

    Runs in a separate process. Neither the upstream helpers nor shared adapter
    files are changed. The existing adapter accepts a subtitle path, not a style.
    """
    entry = RUNTIME/'video-toolchain/local_tools.py'
    spec = importlib.util.spec_from_file_location('talking_head_local_tools', entry)
    local = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(local)
    original_load = local.load_video_use

    def load():
        module = original_load()

        def composite(base, overlays, subtitles, output, directory):
            if not overlays and subtitles is None:
                return module.run(['ffmpeg','-hide_banner','-loglevel','warning','-y',
                                   '-i',str(base),'-c','copy',str(output)])
            inputs, filters, current = ['-i', str(base)], [], '[0:v]'
            for i, overlay in enumerate(overlays, 1):
                inputs += ['-i', str(module.resolve_path(overlay['file'], directory))]
                start = number(overlay['start_in_output'])
                end = start+number(overlay['duration'])
                filters.append(f'[{i}:v]setpts=PTS-STARTPTS+{start}/TB[a{i}]')
                label = f'[v{i}]'
                filters.append(f"{current}[a{i}]overlay=eof_action=pass:repeatlast=0:enable='gte(t,{start})*lt(t,{end})'{label}")
                current = label
            if subtitles is not None:
                path = subtitles.resolve().as_posix().replace(':', r'\:').replace("'", r"\'")
                # ASS declares the chosen full-resolution canvas, so styles
                # scale with the preview instead of using SRT's virtual canvas.
                filters.append(f"{current}subtitles=filename='{path}':force_style='{args.caption_style}'[outv]")
            else:
                filters.append(f'{current}null[outv]')
            graph = ';'.join(filters)
            atomic(directory/'composite-filter.txt', graph.encode('utf-8'))
            module.run(['ffmpeg','-hide_banner','-loglevel','warning','-y', *inputs,
                        '-filter_complex',graph,'-map','[outv]','-map','0:a?',
                        '-c:v','libx264','-preset','fast','-crf','18','-pix_fmt','yuv420p',
                        '-c:a','copy',str(output)])

        module.build_final_composite = composite
        return module

    local.load_video_use = load
    args.build_subtitles = False
    local.video_use_worker(args)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest='command', required=True)
    p = commands.add_parser('prepare')
    p.add_argument('edit_dir', type=Path)
    p.add_argument('sources', nargs='+', type=Path)
    p.add_argument('--mode', choices=('video_analysis', 'audio_transcription', 'cuts_only'), default='video_analysis')
    p.add_argument('--profile', choices=('standard','deep','fast'), default='standard')
    p.add_argument('--clip-seconds', type=int, default=120)
    p.add_argument('--visual-fps', type=float, default=1)
    p.add_argument('--reuse-asr-job')
    p.add_argument('--asr-backend', choices=('doubao2','doubao_turbo'), default='doubao_turbo')
    p.add_argument('--asr-feature', action='append', choices=('emotion','speech_rate','volume'), default=[])
    p.add_argument('--speaker-info', action='store_true')
    p = commands.add_parser('_render-worker', help=argparse.SUPPRESS)
    p.add_argument('edl')
    p.add_argument('output')
    p.add_argument('--fps')
    p.add_argument('--caption-style', required=True)
    p.add_argument('--draft', action='store_true')
    for name in ('status', 'sync', 'advance', 'import-job', 'plan', 'render'):
        p = commands.add_parser(name)
        p.add_argument('edit_dir', type=Path)
        if name == 'advance':
            p.add_argument('--allow-paid-calls', action='store_true')
        if name == 'import-job':
            p.add_argument('job_id')
        if name == 'plan':
            p.add_argument('plan_json', type=Path)
        if name == 'render':
            p.add_argument('output', type=Path)
            p.add_argument('--preview', action='store_true')
    args = parser.parse_args(argv)
    if args.command == '_render-worker':
        return render_worker(args)
    edit = args.edit_dir.absolute()
    if args.command == 'prepare':
        result = prepare(edit,args.sources,args.mode,args.profile,args.clip_seconds,args.visual_fps,args.reuse_asr_job,args.asr_backend,args.asr_feature,args.speaker_info)
    elif args.command == 'status': result = status(edit)
    elif args.command == 'sync': result = sync(edit)
    elif args.command == 'advance': result = advance(edit,args.allow_paid_calls)
    elif args.command == 'import-job': result = import_job(edit,args.job_id)
    elif args.command == 'plan': result = build_plan(edit,args.plan_json)
    else: result = render(edit,args.output.absolute(),args.preview)
    print(json.dumps(result, ensure_ascii=False))
    return result


if __name__ == '__main__':
    sys.dont_write_bytecode = True
    if hasattr(sys.stdout,'reconfigure'):
        sys.stdout.reconfigure(encoding='utf-8')
    try:
        main()
    except (OSError, ValueError, KeyError) as exc:
        print(json.dumps({'state':'needs_review','message':str(exc)},ensure_ascii=False),file=sys.stderr)
        raise SystemExit(1)
