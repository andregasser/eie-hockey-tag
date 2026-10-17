"""A loopback-only browser interface. No files or names leave this computer."""
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
import json
import re
import threading
import traceback
import uuid
import webbrowser

from .engine import ROOT, InputError, build_tag


class GeneratorServer(ThreadingHTTPServer):
    daemon_threads = True

    def __init__(self, port=8765, destination=None):
        super().__init__(('127.0.0.1', port), Handler)
        self.destination = Path(destination or ROOT / 'generated')
        self.jobs = {}
        self.job_lock = threading.Lock()

    @property
    def origin(self):
        return f'http://127.0.0.1:{self.server_port}'


class Handler(BaseHTTPRequestHandler):
    def log_message(self, fmt, *args):
        # Avoid logging player names or downloaded file names.
        pass

    def send_bytes(self, status, data, content_type, filename=None):
        self.send_response(status)
        self.send_header('Content-Type', content_type)
        self.send_header('Content-Length', str(len(data)))
        self.send_header('Cache-Control', 'no-store')
        self.send_header('X-Content-Type-Options', 'nosniff')
        if filename:
            self.send_header('Content-Disposition', f'attachment; filename="{filename}"')
        self.end_headers()
        self.wfile.write(data)

    def send_json(self, status, obj):
        self.send_bytes(status, json.dumps(obj).encode(), 'application/json; charset=utf-8')

    def valid_host(self):
        # Do not allow arbitrary web pages to use a user's local Blender process.
        return self.headers.get('Host') == f'127.0.0.1:{self.server.server_port}'

    def do_GET(self):
        if not self.valid_host():
            return self.send_json(403, {'error': 'Zugriff nur über die lokale Adresse möglich.'})
        if self.path == '/':
            return self.send_bytes(200, Path(__file__).with_name('ui.html').read_bytes(), 'text/html; charset=utf-8')
        match = re.fullmatch(r'/files/([a-f0-9]{32})/(preview|project)', self.path)
        if match and match[1] in self.server.jobs:
            result = self.server.jobs[match[1]]
            path = result[match[2]]
            mime = 'image/png' if match[2] == 'preview' else 'model/3mf'
            return self.send_bytes(200, path.read_bytes(), mime, path.name if match[2] == 'project' else None)
        return self.send_json(404, {'error': 'Datei nicht gefunden. Bitte den Tag erneut erstellen.'})

    def do_POST(self):
        if (not self.valid_host() or self.headers.get('Origin') not in (None, self.server.origin)
                or self.headers.get('X-Tag-Generator') != '1'):
            return self.send_json(403, {'error': 'Bitte den Generator über seine lokale Adresse öffnen.'})
        if self.path != '/api/generate':
            return self.send_json(404, {'error': 'Unbekannte Adresse.'})
        try:
            length = int(self.headers.get('Content-Length', '0'))
            if not 0 < length <= 2048:
                raise ValueError
            payload = json.loads(self.rfile.read(length))
            if not isinstance(payload, dict):
                raise ValueError
        except (ValueError, UnicodeDecodeError):
            return self.send_json(400, {'error': 'Ungültige Eingabe. Bitte Name und Nummer prüfen.'})
        if not self.server.job_lock.acquire(blocking=False):
            return self.send_json(409, {'error': 'Es wird gerade ein Tag erstellt. Bitte kurz warten.'})
        try:
            job = uuid.uuid4().hex
            result = build_tag(payload.get('name'), payload.get('number'), self.server.destination / job)
            self.server.jobs[job] = result
            self.send_json(200, {'preview': f'/files/{job}/preview',
                                'project': f'/files/{job}/project', 'report': result['report']})
        except InputError as exc:
            self.send_json(400, {'error': str(exc)})
        except Exception:
            traceback.print_exc()
            self.send_json(500, {'error': 'Der Tag konnte nicht erstellt werden. Details stehen im Startfenster.'})
        finally:
            self.server.job_lock.release()


def serve(port=8765, open_browser=True):
    server = GeneratorServer(port)
    print(f'EIE Tag-Generator: {server.origin}\nZum Beenden Strg+C drücken.', flush=True)
    if open_browser:
        webbrowser.open(server.origin)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
