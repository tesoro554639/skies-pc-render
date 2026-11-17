# tiny local server: serves the built page, receives each rendered frame as a PNG (POST /frame?i=N), logs, DONE flag
import http.server, sys, os, urllib.parse, time

WEB, OUT, PORT = sys.argv[1], sys.argv[2], int(sys.argv[3])
os.makedirs(OUT, exist_ok=True)

class H(http.server.SimpleHTTPRequestHandler):
    def __init__(self, *a, **k):
        super().__init__(*a, directory=WEB, **k)

    def log_message(self, *a):
        pass

    def do_POST(self):
        try:
            n = int(self.headers.get('Content-Length', 0))
            body = self.rfile.read(n) if n > 0 else b''
            parsed = urllib.parse.urlparse(self.path)
            qs = urllib.parse.parse_qs(parsed.query)

            if parsed.path == '/frame' or parsed.path.startswith('/frame'):
                idx_str = qs.get('i', [None])[0]
                if idx_str is None and 'i=' in self.path:
                    idx_str = self.path.split('i=')[1].split('&')[0]
                if idx_str is not None:
                    i = int(idx_str)
                    tmp = os.path.join(OUT, 'f_%05d.tmp' % i)
                    dst = os.path.join(OUT, 'f_%05d.png' % i)
                    with open(tmp, 'wb') as f:
                        f.write(body)
                    for _ in range(5):
                        try:
                            os.replace(tmp, dst)
                            break
                        except PermissionError:
                            time.sleep(0.05)
            elif parsed.path == '/log' or parsed.path.startswith('/log'):
                msg = body.decode('utf-8', errors='replace')[:400]
                print('LOG', msg, flush=True)
            elif parsed.path == '/done' or parsed.path.startswith('/done'):
                done_file = os.path.join(OUT, 'DONE')
                with open(done_file, 'w', encoding='utf-8') as f:
                    f.write('1')

            self.send_response(200)
            self.send_header('Content-Type', 'text/plain; charset=utf-8')
            self.end_headers()
            self.wfile.write(b'ok')
        except Exception as exc:
            self.send_response(500)
            self.end_headers()
            self.wfile.write(str(exc).encode('utf-8', errors='replace'))

server = http.server.ThreadingHTTPServer(('127.0.0.1', PORT), H)
server.daemon_threads = True
server.allow_reuse_address = True
try:
    server.serve_forever()
except KeyboardInterrupt:
    server.server_close()
