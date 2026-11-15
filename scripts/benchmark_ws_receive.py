"""CPU-only complete-frame parser benchmark; no sockets, TLS or network timing."""
import argparse
import json
import statistics
import struct
import subprocess
import threading
import time
import types
from pathlib import Path

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument("--baseline", required=True, help="Git revision to compare with the working microweb.py")
args = parser.parse_args()
root = Path(__file__).resolve().parents[1]
baseline = subprocess.check_output(["git", "-C", str(root), "show", args.baseline + ":microweb.py"],
                                   text=True, encoding="utf-8")
modules = {}
for name, source in [("before", baseline), ("after", (root / "microweb.py").read_text(encoding="utf-8"))]:
    module = types.ModuleType(name)
    exec(compile(source, name + ".py", "exec"), module.__dict__)
    modules[name] = module

results = {}
for size in (521, 1545):
    payload = b"x" * size
    mask = b"abcd"
    masked = modules["before"]._ws_unmask(payload, mask)
    pieces = (bytes([0x82, 0xfe]), struct.pack("!H", size), mask, masked)
    samples = {"before": [], "after": []}
    for repeat in range(3):
        for name in (["before", "after"] if repeat % 2 == 0 else ["after", "before"]):
            class Socket:
                position = 0
                def recv(self, count):
                    result = pieces[self.position]
                    self.position = (self.position + 1) % len(pieces)
                    assert len(result) == count
                    return result
            ws = modules[name].WebSocket.__new__(modules[name].WebSocket)
            ws._buffer, ws._fragment = bytearray(), bytearray()
            ws._fragment_opcode = None
            ws._closed = threading.Event()
            ws._close_sent, ws.max_bytes, ws.timeout = False, 1048576, 10
            ws._sock = Socket()
            ws._wait = lambda **kwargs: None
            for _ in range(1000): ws._next_message()
            start = time.process_time()
            for _ in range(40000): ws._next_message()
            samples[name].append((time.process_time() - start) / 40000 * 1e6)
    before, after = (statistics.median(samples[name]) for name in ("before", "after"))
    results[size] = dict(before_us=round(before, 3), after_us=round(after, 3),
                         reduction_percent=round((1 - after / before) * 100, 1))
print(json.dumps(results, indent=2))
