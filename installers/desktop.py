"""Launch the bundled Core HR server; local data belongs to the installing user."""
import argparse
from pathlib import Path
import runpy
import sys
import threading
import time
import urllib.request
import webbrowser

PROGRAM = Path(__file__).resolve().parent
sys.path[:0] = [str(PROGRAM / 'app'), str(PROGRAM / 'vendor'), str(PROGRAM)]
from installer import checked_root, workspace_lock


def browser_when_ready(origin):
    def wait():
        client = urllib.request.build_opener(urllib.request.ProxyHandler({}))
        for _ in range(80):
            try:
                with client.open(origin + '/api/health/live', timeout=1) as response:
                    if response.status == 200: webbrowser.open(origin); return
            except OSError: pass
            time.sleep(.1)
    threading.Thread(target=wait, daemon=True).start()


def main():
    parser = argparse.ArgumentParser(description='OpenPeople on your computer. Close with Ctrl+C; records are preserved.')
    parser.add_argument('--db', type=Path, required=True)
    parser.add_argument('--port', type=int, default=8000)
    parser.add_argument('--no-browser', action='store_true')
    parser.add_argument('--public-origin')
    parser.add_argument('--production', action='store_true')
    arguments = sys.argv[1:]
    tool = None
    tool_arguments = []
    if '--tool' in arguments:
        position = arguments.index('--tool')
        if len(arguments) <= position + 1: parser.error('Choose backup, manage, setup or acceptance after --tool.')
        tool = arguments[position + 1]
        tool_arguments = arguments[position + 2:]
        arguments = arguments[:position]
        if tool not in ('backup', 'manage', 'setup', 'acceptance'): parser.error('Unknown maintenance tool.')
    args = parser.parse_args(arguments)
    if not 1 <= args.port <= 65535: parser.error('Choose a valid TCP port.')
    root = checked_root(args.db.parent.parent)
    if args.db.absolute() != root / 'data/openpeople.db': parser.error('Use the installed private data/openpeople.db workspace.')
    try:
        with workspace_lock(root):
            if tool:
                script = {'backup': 'backup.py', 'manage': 'manage.py', 'setup': 'scripts/setup_workspace.py', 'acceptance': 'scripts/accept_core_hr.py'}[tool]
                # CLI helpers are included in clean source and use the same vendor path.
                if tool in ('manage', 'setup') or tool == 'backup' and tool_arguments and tool_arguments[0] in ('configure', 'create', 'run', 'status') or tool == 'acceptance' and tool_arguments and tool_arguments[0] in ('installation', 'reference'):
                    if '--db' in tool_arguments: parser.error('The wrapper already selects the installed database.')
                    tool_arguments += ['--db', str(args.db)]
                sys.argv = [script, *tool_arguments]
                runpy.run_path(str(PROGRAM / 'app' / script), run_name='__main__')
                return
            from serving import serve_workspace
            serve_workspace(args.db, port=args.port, public_origin=args.public_origin, production=args.production, product_profile='core-hr', on_ready=None if args.no_browser or args.public_origin else browser_when_ready)
    except KeyboardInterrupt: pass
    except (ValueError, OSError) as error: parser.exit(1, str(error) + '\n')


if __name__ == '__main__': main()
