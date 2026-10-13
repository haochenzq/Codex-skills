"""Focused offline checks for per-worker hashes and content-based clip reuse."""
from pathlib import Path
import contextlib
import importlib.util
import io
import json
import os
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

HERE = Path(__file__).resolve().parent
ENTRY = Path(os.environ.get('VIDEO_TOOLS_TEST_ENTRY', HERE/'local_tools.py'))
spec = importlib.util.spec_from_file_location('local_hash_cache_entry', ENTRY)
tools = importlib.util.module_from_spec(spec)
spec.loader.exec_module(tools)


class RenderHashTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='hash-cache-test-', dir=HERE)
        self.root = Path(self.temp.name)
        self.a = self.root/'source.mp4'
        self.a.write_bytes(b'source A original content')
        self.b = self.root/'other/source.mp4'
        self.b.parent.mkdir()
        self.b.write_bytes(b'source B different content')
        self.edl = self.root/'edl.json'
        self.reads = []

    def tearDown(self):
        self.temp.cleanup()

    def render(self, ranges, cache=True, version='v1'):
        self.edl.write_text(json.dumps({'sources': {'a':str(self.a), 'alias':'source.mp4', 'b':str(self.b)},
                                      'ranges':ranges, 'canvas':[1920,1080], 'cache_segments':cache}), encoding='utf-8')
        args = SimpleNamespace(edl=str(self.edl), output=str(self.root/(version+'.mp4')),
                               fps='30', draft=False, build_subtitles=False)
        def run(argv):
            Path(argv[-1]).write_bytes(b'encoded fixture')
        def concat(segments, target, edit):
            target.write_bytes(b'concatenated fixture')
        def composite(base, overlays, subtitles, target, edit):
            target.write_bytes(b'composited fixture')
        def normalize(source, target, preview=False):
            target.write_bytes(b'normalized fixture')
        module = SimpleNamespace(resolve_path=lambda p,e:(Path(p) if Path(p).is_absolute() else e/p).resolve(),
                                 parse_fps=str, resolve_grade_filter=lambda _:None, is_hdr_source=lambda _:False,
                                 run=run, concat_segments=concat, build_final_composite=composite,
                                 measure_loudness=lambda _:{'input_i':-20}, apply_loudnorm_two_pass=normalize)
        probe = SimpleNamespace(stdout=json.dumps({'format':{'duration':'10'}, 'streams':[{'codec_type':'audio'}]}))
        original_open = Path.open
        def opened(path, mode='r', *rest, **kwargs):
            if mode=='rb' and path.resolve() in (self.a,self.b):
                self.reads.append(path.resolve())
            return original_open(path,mode,*rest,**kwargs)
        with patch.object(tools,'load_video_use',return_value=module), \
             patch.object(tools,'environment',return_value={}), \
             patch.object(tools.subprocess,'run',return_value=probe), \
             patch.object(Path,'open',opened), contextlib.redirect_stdout(io.StringIO()):
            tools.video_use_worker(args)
        return set((self.root/'clips_pcm').glob('*.mkv'))

    def test_same_source_alias_hashes_once_distinct_sources_separately(self):
        self.render([{'source':'a','start':0,'end':1}, {'source':'alias','start':1,'end':2},
                     {'source':'b','start':2,'end':3}])
        self.assertEqual(self.reads.count(self.a),1)
        self.assertEqual(self.reads.count(self.b),1)

    def test_new_worker_rechecks_content_and_invalidates_changed_source(self):
        ranges=[{'source':'a','start':0,'end':1},{'source':'alias','start':1,'end':2}]
        first=self.render(ranges)
        self.assertEqual(self.render(ranges,version='v2'),first)
        self.a.write_bytes(b'source A changed content')
        changed=self.render(ranges,version='v3')
        self.assertEqual(self.reads.count(self.a),3)
        self.assertEqual(len(changed-first),2)
        self.assertTrue(all(p.is_file() for p in first))

    def test_uncached_path_does_not_add_hash_reads(self):
        self.render([{'source':'a','start':0,'end':1},{'source':'alias','start':1,'end':2}],cache=False)
        self.assertEqual(self.reads,[])


if __name__=='__main__':
    unittest.main(verbosity=2)
