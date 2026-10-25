"""Synthetic lifecycle/data-join demonstration. No models, research code or GPU work."""
import json
import queue
import threading
from pathlib import Path

from microweb import App, Component, Response


def create_component(settings):
    root = Path(settings['data_dir'])
    sources = [Path(path) for path in settings.get('download_sources', [])]
    if not root.is_absolute() or any(not path.is_absolute() for path in sources):
        raise ValueError('the example launcher must supply absolute paths')
    web, stop, pending = App(), threading.Event(), queue.Queue()
    lock, worker = threading.Lock(), [None]
    state = {'service': 'not started', 'completed': []}

    def recordings():
        # A deliberately narrow, read-only consumer of downloader state.
        rows = []
        for source in sources:
            for saved in sorted(source.glob('*/state.json')):
                data = json.loads(saved.read_text(encoding='utf-8'))
                for candidate in data.get('candidates', []):
                    download = candidate.get('download') or {}
                    file = (saved.parent / str(download.get('file', '')).replace('\\', '/')).resolve()
                    if (download.get('status') != 'done' or candidate.get('decision') == 'reject'
                            or not file.is_relative_to(saved.parent.resolve()) or not file.is_file()):
                        continue
                    rows.append({'reader': data.get('reader_id', saved.parent.name),
                                 'title': candidate.get('title'), 'file': str(file),
                                 'quality': download.get('quality')})
        return rows

    def work():
        while not stop.is_set() or not pending.empty():
            try:
                item = pending.get(timeout=0.1)
            except queue.Empty:
                continue
            with lock:
                state['completed'].append(item)
            pending.task_done()

    def start():
        root.mkdir(parents=True, exist_ok=True)
        state['service'] = 'running'
        worker[0] = threading.Thread(target=work, name='synthetic-workbench', daemon=True)
        worker[0].start()

    def close():
        stop.set()
        if worker[0] is not None:
            worker[0].join()
        with lock:
            state['service'] = 'stopped'
            (root / 'last_shutdown.json').write_text(json.dumps(state, indent=2) + '\n', encoding='utf-8')

    @web.get('/')
    def page(req):
        return Response('''<!doctype html><html lang="en"><meta charset="utf-8">
<title>Synthetic workbench</title><style>body{font:16px system-ui;max-width:850px;margin:40px auto;padding:20px}
button{padding:10px}pre{white-space:pre-wrap;background:#f3f5f8;padding:20px}</style>
<h1>Synthetic workbench</h1><p>A shell integration example. No voice generation or research jobs.</p>
<p>Reads completed, present, non-rejected recordings from the configured download library.</p>
<button id="run">Run synthetic task</button><pre id="status"></pre>
<script>
async function refresh(){const s=await(await fetch('api/status')).json();document.getElementById('status').textContent=JSON.stringify(s,null,2);}
document.getElementById('run').onclick=async()=>{await fetch('api/work',{method:'POST',headers:{'Content-Type':'application/json'},body:'{}'});await refresh();};
refresh();setInterval(refresh,2000);
</script></html>''', content_type='text/html; charset=utf-8')

    @web.get('/api/status')
    def status(req):
        with lock:
            snapshot = {**state, 'completed': list(state['completed'])}
        return {**snapshot, 'recordings': recordings()}

    @web.post('/api/work')
    def submit(req):
        req.json()
        pending.put({'recordings_seen': len(recordings())})
        return {'queued': True}, 202

    return Component('voices', 'Synthetic workbench', web, start, close)
