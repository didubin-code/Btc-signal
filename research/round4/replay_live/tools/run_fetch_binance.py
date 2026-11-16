"""Wrapper only: runs the UNMODIFIED replay_pub/tools/fetch_binance_1s.py under `python3 -I` (isolated mode drops the script
directory from sys.path, so its bare `import http_util` needs the tools directory inserted first). No logic of its own.
  python3 -I run_fetch_binance.py <tools dir> <fetch_binance_1s.py arguments...>"""
import runpy, sys
tools = sys.argv[1]
sys.path.insert(0, tools)
sys.argv = [tools + '/fetch_binance_1s.py'] + sys.argv[2:]
runpy.run_path(tools + '/fetch_binance_1s.py', run_name='__main__')
