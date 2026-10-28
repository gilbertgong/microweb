"""Bundled synthetic apps: stdlib only, no models, writes, probes or background jobs."""
import html
import math
from pathlib import Path
import threading
import time

from microweb import App, Component, Response

_lock = threading.Lock()
_completed = []


def _component(id, label, content):
    app = App()
    @app.get('/')
    def home(req):
        page = (content if content.startswith('<!doctype') else
                '<!doctype html><html lang="en"><head><meta charset="utf-8">'
                        '<meta name="viewport" content="width=device-width,initial-scale=1">'
                        '<style>body{font:15px system-ui;margin:32px;color:#243047;background:#f4f6fa}'
                        'main{max-width:900px;margin:auto}h1{font-size:26px}small{color:#57657a}'
                        'table{width:100%;border-collapse:collapse;background:white}th,td{text-align:left;padding:12px;border-bottom:1px solid #dce1ea}'
                        'button{font:inherit;padding:7px 12px;cursor:pointer;border:1px solid #b9c8de;border-radius:5px;background:white}'
                        'li{padding:6px}#message{padding:12px 0}</style></head><body><main>' + content + '</main></body></html>')
        page = page.replace('<head>', '<head><base href="' + html.escape(req.url(), quote=True) + '">', 1)
        return Response(page, content_type='text/html; charset=utf-8')
    @app.get('/api/status')
    def status(req):
        with _lock:
            return {'synthetic': True, 'component': id, 'mount_prefix': req.root_path,
                    'completed': list(_completed)}
    return Component(id, label, app)


def machine(settings):
    component = _component('demo-machine', 'Machine (demo)',
                           Path(__file__).with_name('machine.html').read_text(encoding='utf-8'))
    @component.app.get('/api/machine')
    def readings(req):
        times = [time.monotonic() - 2*i for i in reversed(range(60))]
        cpu = [round(24 + 12*math.sin(t/8), 1) for t in times]
        return dict(history_seconds=120, cpu=dict(cores=16,busy_pct=cpu[-1],average_pct=sum(cpu)/60,history=cpu),
                    memory=dict(ram_gb=32,ram_free_gb=19,commit_limit_gb=64,commit_free_gb=42))
    return component


def library(settings):
    return _component('demo-library', 'Library (demo)',
                      '<h1>Library</h1><p>Synthetic panel one. These are fabricated sample records.</p>'
                      '<table><thead><tr><th>Item</th><th>Kind</th><th>State</th></tr></thead><tbody>' +
                      ''.join(f'<tr><td>Example {i}</td><td>{kind}</td><td>Ready</td></tr>'
                              for i, kind in enumerate(['Document','Audio','Image','Dataset','Notebook','Report'],1)) +
                      '</tbody></table><p><a href="api/status">View this component’s JSON</a></p>'
                      '<small>The Machine banner appears above both panels. This app also runs standalone.</small>')


def workbench(settings):
    component = _component('demo-workbench', 'Workbench (demo)',
                      '<h1>Workbench</h1><p>Synthetic panel two. Try a local API interaction.</p>'
                      '<button id="run">Run demo task</button><div id="message" role="status"></div><ul id="results"></ul>'
                      '<small>No worker, file output or computation: each click records an in-memory demo result.</small>'
                      '<script>async function refresh(){const r=await fetch("api/status");const s=await r.json();'
                      'document.getElementById("results").replaceChildren(...s.completed.map(text=>{const li=document.createElement("li");li.textContent=text;return li}));}'
                      'document.getElementById("run").onclick=async()=>{const r=await fetch("api/run",{method:"POST"});'
                      'document.getElementById("message").textContent=r.ok?"Demo task complete":"Demo task failed";refresh()};refresh();</script>')
    @component.app.post('/api/run')
    def run(req):
        with _lock:
            _completed.append(f'Demo result {len(_completed)+1}')
            return {'completed': len(_completed)}
    return component
