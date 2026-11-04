"""Loopback-only controls for unchanged XT660 firmware running in µCsim."""
import argparse
import csv
import io
import json
import secrets
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from engine import Engine
from runner import ROOT, registered_image

HERE = Path(__file__).resolve().parent


def available_images():
    result = []
    for row in json.loads((ROOT/'firmware/registry.json').read_text(encoding='utf-8'))['images']:
        try:
            registered_image(row['id'])
        except ValueError:
            continue
        result.append(dict(id=row['id'], label=row['label']+' · '+row['variant']))
    return result


class Dashboard:
    def __init__(self, executable, wsl=False):
        self.executable, self.wsl = executable, wsl
        self.engine = None
        self.lock = threading.Lock()
        self.token = secrets.token_urlsafe(32)
        self.images = available_images()
        self.error = ''

    def state(self):
        if self.engine is None:
            return dict(loaded=False, images=self.images, error=self.error)
        state = self.engine.snapshot()
        state.update(loaded=True, images=self.images, error=self.error,
                     storage=self.engine.storage_origin,
                     trace=list(self.engine.trace)[-600:], transcript=self.engine.transcript[-30:])
        return state

    def action(self, data):
        action = data.get('action')
        if action == 'load':
            if data.get('image') not in {r['id'] for r in self.images}:
                raise ValueError('Select a complete registered BIN')
            if self.engine:
                self.engine.close()
                self.engine = None
            self.error = ''
            self.engine = Engine(self.executable, data['image'], self.wsl)
        else:
            if self.engine is None:
                raise ValueError('Load a BIN first')
            if action == 'step':
                self.engine.step(data.get('instructions', 100000))
            elif action == 'adc':
                self.engine.set_adc(data.get('channel'), data.get('value'))
            elif action == 'crank':
                self.engine.crank(data.get('pitch', 1600), data.get('patterns', 24), data.get('uniform') is True)
            elif action == 'stop-crank':
                self.engine.stop_crank()
            elif action == 'authenticate':
                self.engine.authenticate()
            elif action == 'meter':
                self.engine.exchange(0xfe)
                self.engine.exchange(0x01)
            elif action == 'verify':
                self.engine.verify_flash()
            else:
                raise ValueError('Unknown control')
        return self.state()

    def close(self):
        with self.lock:
            if self.engine:
                self.engine.close()
                self.engine = None


def make_server(dashboard, port):
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def reply(self, status, content, mime='application/json'):
            if isinstance(content, (dict, list)):
                content = json.dumps(content).encode('utf-8')
            elif isinstance(content, str):
                content = content.encode('utf-8')
            self.send_response(status)
            self.send_header('Content-Type', mime)
            self.send_header('Content-Length', str(len(content)))
            self.send_header('Cache-Control', 'no-store')
            self.send_header('X-Content-Type-Options', 'nosniff')
            self.send_header('Content-Security-Policy', "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self'; connect-src 'self'; frame-ancestors 'none'; base-uri 'none'")
            self.end_headers()
            self.wfile.write(content)

        def local(self):
            return self.headers.get('Host') == f'127.0.0.1:{self.server.server_port}'

        def do_GET(self):
            if not self.local():
                return self.reply(403, {'error':'Use the loopback URL printed at startup'})
            assets = {'/': ('dashboard.html','text/html; charset=utf-8'),
                      '/dashboard.css': ('dashboard.css','text/css'),
                      '/dashboard.js': ('dashboard.js','text/javascript')}
            if self.path in assets:
                name,mime = assets[self.path]
                content = (HERE/'web'/name).read_text(encoding='utf-8').replace('{{TOKEN}}', dashboard.token)
                return self.reply(200, content, mime)
            if self.path == '/logo.png':
                return self.reply(200,(ROOT/'site/assets/yamaha-motor-logo.png').read_bytes(),'image/png')
            with dashboard.lock:
                try:
                    if self.path == '/api/state':
                        return self.reply(200,dashboard.state())
                    if dashboard.engine and self.path == '/trace.csv':
                        output=io.StringIO(newline='')
                        writer=csv.DictWriter(output,fieldnames=['cycle','kind','channel','value','pc'])
                        writer.writeheader();writer.writerows(dashboard.engine.trace)
                        return self.reply(200,output.getvalue(),'text/csv')
                    if dashboard.engine and self.path == '/storage.bin':
                        return self.reply(200,dashboard.engine.external_storage(),'application/octet-stream')
                except (RuntimeError, ValueError, OSError) as error:
                    return self.reply(500,{'error':str(error)})
            self.reply(404,{'error':'Not found'})

        def do_POST(self):
            origin=f'http://127.0.0.1:{self.server.server_port}'
            if not self.local() or self.headers.get('Origin') not in (None,origin) or not secrets.compare_digest(self.headers.get('X-XT660-Token',''),dashboard.token):
                return self.reply(403,{'error':'Invalid local session'})
            if self.path != '/api/action':
                return self.reply(404,{'error':'Not found'})
            try:
                length=int(self.headers.get('Content-Length','0'))
                if not 1 <= length <= 4096:
                    raise ValueError('Invalid request size')
                data=json.loads(self.rfile.read(length))
                if not isinstance(data,dict):
                    raise ValueError('Expected a control object')
                with dashboard.lock:
                    state=dashboard.action(data)
                self.reply(200,state)
            except (ValueError, TypeError) as error:
                self.reply(400,{'error':str(error)})
            except (RuntimeError, OSError) as error:
                dashboard.error=str(error)
                self.reply(500,{'error':str(error)})
    return ThreadingHTTPServer(('127.0.0.1',port),Handler)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--ucsim',required=True)
    parser.add_argument('--wsl',action='store_true')
    parser.add_argument('--port',type=int,default=8766)
    args=parser.parse_args()
    dashboard=Dashboard(args.ucsim,args.wsl)
    server=make_server(dashboard,args.port)
    print(f'XT660 emulator: http://127.0.0.1:{server.server_port}/',flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
        dashboard.close()


if __name__=='__main__':
    main()
