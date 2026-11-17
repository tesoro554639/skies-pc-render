# Local & Cloud frame renderer: renders frames of the built page (engine/web) in headless browsers.
#   python render.py --web ENGINE/web --out FRAMES_DIR (--list 0,30,60 | --range 0-1475) [--w 540] [--procs 2] [--ms 1] [--sm 2048] [--mode gpu|cpu]
import argparse, os, subprocess, sys, time, shutil, socket

def find_free_port(start_port=8840, exclude=None):
    port = start_port
    exclude = exclude or set()
    while port < 65535:
        if port not in exclude:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
                try:
                    s.bind(('127.0.0.1', port))
                    return port
                except OSError:
                    pass
        port += 1
    raise RuntimeError("No free port available in range 8840-65535")

def kill_proc_tree(p):
    if p is None or p.poll() is not None:
        return
    if os.name == 'nt':
        try:
            flags = subprocess.CREATE_NO_WINDOW if hasattr(subprocess, 'CREATE_NO_WINDOW') else 0
            subprocess.run(['taskkill', '/F', '/T', '/PID', str(p.pid)],
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=4,
                           creationflags=flags)
        except Exception:
            try: p.kill()
            except Exception: pass
    else:
        try:
            p.terminate()
            p.wait(timeout=2)
        except Exception:
            try: p.kill()
            except Exception: pass

def rescue_frames(out_dir, work_dirs):
    moved = 0
    for d in work_dirs:
        if not os.path.isdir(d):
            continue
        try:
            for x in sorted(os.listdir(d)):
                if x.startswith('f_') and x.endswith('.png'):
                    src = os.path.join(d, x)
                    dst = os.path.join(out_dir, x)
                    if not os.path.exists(dst):
                        try:
                            os.replace(src, dst)
                            moved += 1
                        except OSError:
                            try:
                                shutil.copyfile(src, dst)
                                os.remove(src)
                                moved += 1
                            except OSError:
                                pass
        except Exception:
            pass
    return moved

def parse_frames(list_arg, range_arg):
    if list_arg:
        return [int(x.strip()) for x in list_arg.split(',') if x.strip().isdigit()]
    if range_arg:
        if '-' in range_arg:
            parts = range_arg.split('-')
            return list(range(int(parts[0]), int(parts[1]) + 1))
        return [int(range_arg.strip())]
    raise ValueError("Either --list or --range must be specified")

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--web', required=True, help="Path to built WebGL folder containing index.html")
    ap.add_argument('--out', required=True, help="Directory to save rendered frames")
    ap.add_argument('--list', help="Comma-separated frame numbers, e.g. 0,10,20")
    ap.add_argument('--range', help="Frame range, e.g. 0-1128 or single frame 50")
    ap.add_argument('--w', type=int, default=540, help="Render width (default: 540)")
    ap.add_argument('--procs', type=int, default=2, help="Number of concurrent browser workers (default: 2)")
    ap.add_argument('--ms', type=int, default=1, help="MSAA samples (default: 1)")
    ap.add_argument('--sm', type=int, default=2048, help="Shadow map resolution (default: 2048)")
    ap.add_argument('--mode', choices=['gpu', 'cpu'], help="Override runner mode (gpu or cpu)")
    ap.add_argument('--runner', help="Explicit path to runner js file")
    a = ap.parse_args()

    H = os.path.dirname(os.path.abspath(__file__))
    fr = parse_frames(a.list, a.range)
    os.makedirs(a.out, exist_ok=True)

    # First rescue any previous worker frames that may already be in _w*
    existing_work = [os.path.join(a.out, d) for d in os.listdir(a.out) if d.startswith('_w') and os.path.isdir(os.path.join(a.out, d))]
    rescued = rescue_frames(a.out, existing_work)
    if rescued:
        print(f"Rescued {rescued} existing frames from worker folders.", flush=True)

    todo = [f for f in fr if not os.path.exists(os.path.join(a.out, 'f_%05d.png' % f))]
    print('frames', len(fr), 'to render', len(todo), flush=True)
    if not todo:
        print('RENDER DONE', flush=True)
        sys.exit(0)

    # Determine runner script
    if a.runner:
        runner_js = os.path.abspath(a.runner)
    elif a.mode == 'gpu':
        runner_js = os.path.join(H, 'run.js.gpu') if os.path.isfile(os.path.join(H, 'run.js.gpu')) else os.path.join(H, 'run.js')
    elif a.mode == 'cpu':
        runner_js = os.path.join(H, 'run.js.cpu') if os.path.isfile(os.path.join(H, 'run.js.cpu')) else os.path.join(H, 'run.js')
    else:
        runner_js = os.path.join(H, 'run.js')

    n = max(1, min(a.procs, len(todo)))
    parts = [todo[i::n] for i in range(n)]

    procs = []
    node_procs = []
    work = []
    log_files = []
    used_ports = set()

    try:
        for j, part in enumerate(parts):
            d = os.path.join(a.out, '_w%d' % j)
            shutil.rmtree(d, ignore_errors=True)
            os.makedirs(d, exist_ok=True)

            port = find_free_port(start_port=8840 + j * 2, exclude=used_ports)
            used_ports.add(port)

            srv_log_f = open(d + '.srv.log', 'w', encoding='utf-8', errors='replace')
            node_log_f = open(d + '.log', 'w', encoding='utf-8', errors='replace')
            log_files.extend([srv_log_f, node_log_f])

            flags = subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0
            sp = subprocess.Popen([sys.executable, os.path.join(H, 'srv.py'), a.web, d, str(port)],
                                  stdout=srv_log_f, stderr=subprocess.STDOUT, creationflags=flags)
            procs.append(sp)
            time.sleep(0.6)

            np = subprocess.Popen(['node', runner_js, str(port), ','.join(map(str, part)), d,
                                   str(a.w), str(a.ms), str(a.sm)],
                                  stdout=node_log_f, stderr=subprocess.STDOUT, cwd=H, creationflags=flags)
            procs.append(np)
            node_procs.append(np)
            work.append(d)

        t0 = time.time()
        last = -1
        while True:
            done = sum(len([x for x in os.listdir(d) if x.endswith('.png')]) for d in work if os.path.isdir(d))
            if done != last and (done % 20 == 0 or done == len(todo)):
                el = time.time() - t0
                eta = el / max(done, 1) * (len(todo) - done)
                print('progress %d/%d  elapsed %dm%02ds  eta %dm%02ds' %
                      (done, len(todo), el // 60, el % 60, eta // 60, eta % 60), flush=True)
            last = done
            if all(os.path.exists(os.path.join(d, 'DONE')) for d in work) or done >= len(todo):
                break
            if all(p.poll() is not None for p in node_procs):
                print('WORKERS EXITED', flush=True)
                break
            if time.time() - t0 > 6 * 3600:
                print('TIMEOUT', flush=True)
                break
            time.sleep(2)
    finally:
        # Move rendered frames immediately
        rescue_frames(a.out, work)
        # Kill all processes in process trees
        for p in procs:
            kill_proc_tree(p)
        # Close all opened log files
        for f in log_files:
            try: f.close()
            except Exception: pass

    # Report errors if any
    errs = []
    for d in work:
        log_path = d + '.log'
        srv_log_path = d + '.srv.log'
        if os.path.isfile(log_path):
            with open(log_path, 'r', encoding='utf-8', errors='replace') as f:
                for line in f:
                    if any(k in line for k in ('PAGEERR', 'BROWSER_LAUNCH_ERR', 'CONSOLE_ERR', 'PAGE_GOTO_ERR')):
                        errs.append(line.strip())
        if os.path.isfile(srv_log_path):
            with open(srv_log_path, 'r', encoding='utf-8', errors='replace') as f:
                for line in f:
                    if 'ERROR' in line or 'REJECT' in line:
                        errs.append(line.strip())

    for l in errs[:10]:
        print(l)

    miss = [f for f in fr if not os.path.exists(os.path.join(a.out, 'f_%05d.png' % f))]
    print('missing', len(miss), miss[:20])
    if not miss:
        print('RENDER DONE', flush=True)
        sys.exit(0)
    else:
        print('RENDER INCOMPLETE', flush=True)
        sys.exit(1)

if __name__ == '__main__':
    main()
