"""One-file framework, standard-library WebSocket echo demo: python examples/websocket_echo.py."""
import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from microweb import App, Response

app, demo = App(), App()
app.mount('/demo', demo)


@app.get('/')
def home(req):
    return Response(status=302, headers={'Location': req.url('/demo/')})


@demo.get('/')
def page(req):
    return Response(r'''<!doctype html><html lang="en"><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Microweb WebSocket echo</title>
<style>body{font:16px system-ui;max-width:760px;margin:50px auto;padding:0 20px}
button,input{font:inherit;padding:8px}pre{white-space:pre-wrap;background:#f1f4f8;padding:16px}</style>
<h1>WebSocket echo</h1><p>HTTP and WebSockets share one port, mounted under /demo/.</p>
<p id="status" role="status">Connecting…</p>
<form id="form"><label>Message <input id="message" value="Hello microweb"></label>
<button id="send" disabled>Send</button></form>
<p><button id="large" disabled>Send 500 KB</button> <button id="reconnect">Reconnect</button></p>
<pre id="log" aria-live="polite"></pre>
<script>
const status=document.getElementById('status'),log=document.getElementById('log');let ws;
function connect(){
 if(ws)ws.close();
 const url=new URL('events',location.href);url.protocol=location.protocol==='https:'?'wss:':'ws:';
 const current=new WebSocket(url);ws=current;
 current.onopen=()=>{if(ws!==current)return;status.textContent='Connected';enable(true);};
 current.onmessage=e=>{if(ws!==current)return;log.textContent='Received '+new TextEncoder().encode(e.data).length+' bytes'+(e.data.length<200?': '+e.data:'.')+'\n'+log.textContent.slice(0,2000);};
 current.onclose=e=>{if(ws!==current)return;status.textContent='Closed ('+e.code+'). Use Reconnect to try again.';enable(false);};
 current.onerror=()=>{if(ws===current)status.textContent='Connection error';};
}
function enable(ready){document.getElementById('send').disabled=!ready;document.getElementById('large').disabled=!ready;}
document.getElementById('form').onsubmit=e=>{e.preventDefault();if(ws.readyState===WebSocket.OPEN)ws.send(document.getElementById('message').value);};
document.getElementById('large').onclick=()=>{if(ws.readyState===WebSocket.OPEN)ws.send('x'.repeat(500000));};
document.getElementById('reconnect').onclick=connect;connect();
</script></html>''', content_type='text/html; charset=utf-8')


@demo.websocket('/events')
def echo(ws):
    for message in ws:
        ws.send(message)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--port', type=int, default=8769)
    args = parser.parse_args()
    app.run('127.0.0.1', args.port, on_ready=lambda: print(
        f'Open http://127.0.0.1:{args.port}/', flush=True))
