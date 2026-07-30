"""Add the income-tax-rag MCP server to claude_desktop_config.json, safely.

    python scripts/add_mcp_server.py

WHY A SCRIPT AND NOT NOTEPAD
  The config file can run to millions of characters. Editing that by hand risks
  a single misplaced character that breaks the JSON, disconnects every existing
  server, and gives no error message pointing at what happened.

WHAT THIS DOES
  1. Backs the file up first, with a timestamp. Nothing is overwritten.
  2. Parses it. If it will not parse, it stops and changes nothing --
     better to find that out now than after writing.
  3. Adds ONE key under "mcpServers", leaving everything else untouched.
  4. Refuses to clobber an existing "income-tax-rag" entry unless asked.

Run it twice and it will tell you it is already there, not duplicate it.

PATHS ARE DERIVED, NOT HARDCODED
  Every path below is worked out at runtime from where this file sits and which
  interpreter is running it. That is deliberate: an earlier version of this
  script had three absolute paths baked in, which made it correct on exactly one
  machine and silently wrong on every other.
"""
import datetime
import json
import os
import shutil
import sys

# WHERE THE CONFIG ACTUALLY LIVES -- this cost an hour on 29 Jul 2026.
#
# Claude Desktop installed from the Microsoft Store is an MSIX-packaged app, so
# Windows redirects its AppData into a per-package sandbox. Writing to the
# obvious path (%APPDATA%\Claude) produces a perfectly valid config that the app
# never reads. The symptom is not an error -- it is SILENCE: no server, and no
# mcp-server-*.log at all, because no start was ever attempted.
#
# The real path is confirmed by Settings -> Developer -> Edit Config, which
# opens the folder the app truly uses.
if os.name == 'nt':
    STORE_DIR = os.path.join(
        os.environ['LOCALAPPDATA'],
        'Packages', 'Claude_pzs8sxrjxfjjc', 'LocalCache', 'Roaming', 'Claude',
    )
    PLAIN_DIR = os.path.join(os.environ['APPDATA'], 'Claude')
    # Prefer the Store sandbox if that install exists.
    CONFIG_DIR = STORE_DIR if os.path.isdir(STORE_DIR) else PLAIN_DIR
elif sys.platform == 'darwin':
    CONFIG_DIR = os.path.expanduser(
        '~/Library/Application Support/Claude')
else:
    CONFIG_DIR = os.path.expanduser('~/.config/Claude')

CONFIG = os.path.join(CONFIG_DIR, 'claude_desktop_config.json')

HERE = os.path.dirname(os.path.abspath(__file__))
SERVER_PY = os.path.join(HERE, 'mcp_server.py')

# CHROMA_DIR is set explicitly rather than left to the server to guess. If "~"
# resolved differently under Claude Desktop's environment than it does in the
# shell, Chroma would silently create an EMPTY new database and return zero
# chunks -- which looks like a broken index but is really a path problem.
# Override by exporting CHROMA_DIR before running this script.
CHROMA_DIR = os.environ.get(
    'CHROMA_DIR', os.path.join(os.path.expanduser('~'), '.income_tax_rag_chroma'))

SERVER_NAME = 'income-tax-rag'
SERVER_ENTRY = {
    # sys.executable, not the bare word "python". Claude Desktop launches this
    # server with its own environment, which may not have Python on PATH even
    # though the shell does. That failure is silent -- the server just never
    # appears -- so pin it to the interpreter running this script.
    "command": sys.executable,
    "args": [SERVER_PY],
    "env": {"CHROMA_DIR": CHROMA_DIR},
}

print(f"config: {CONFIG}")
print(f"python: {sys.executable}")
print(f"server: {SERVER_PY}")
print(f"chroma: {CHROMA_DIR}")

# Fail early and loudly if the server file is not where it should be, rather
# than writing a config that points at nothing.
if not os.path.isfile(SERVER_PY):
    print(f"\nSTOPPED. mcp_server.py not found next to this script.")
    print("Run this from inside the repo's scripts/ folder. Nothing changed.")
    sys.exit(1)

if not os.path.isfile(CONFIG):
    print("Not found. Creating a fresh config with just this server.")
    os.makedirs(os.path.dirname(CONFIG), exist_ok=True)
    with open(CONFIG, 'w', encoding='utf-8') as f:
        json.dump({"mcpServers": {SERVER_NAME: SERVER_ENTRY}}, f, indent=2)
    print("Done. Fully quit and reopen Claude Desktop.")
    sys.exit(0)

size = os.path.getsize(CONFIG)
print(f"size  : {size:,} bytes")

# 1. Back up BEFORE reading, let alone writing.
stamp = datetime.datetime.now().strftime('%Y%m%d-%H%M%S')
backup = f"{CONFIG}.backup-{stamp}"
shutil.copy2(CONFIG, backup)
print(f"backup: {backup}")

# 2. Parse. Stop on failure -- do not write to a file we do not understand.
try:
    with open(CONFIG, encoding='utf-8') as f:
        cfg = json.load(f)
except json.JSONDecodeError as e:
    print(f"\nSTOPPED. The existing config is not valid JSON: {e}")
    print("Nothing was changed. The backup above is identical to the original.")
    sys.exit(1)

if not isinstance(cfg, dict):
    print("\nSTOPPED. Top level of the config is not an object. Nothing changed.")
    sys.exit(1)

servers = cfg.setdefault('mcpServers', {})
print(f"existing servers: {len(servers)}")
for name in servers:
    print(f"  - {name}")

if SERVER_NAME in servers:
    print(f"\n'{SERVER_NAME}' is already configured.")
    if servers[SERVER_NAME] == SERVER_ENTRY:
        print("It matches what this script would write. Nothing to do.")
        sys.exit(0)
    print("It differs from what this script would write. Overwrite? (y/n): ", end='')
    if input().strip().lower() != 'y':
        print("Left alone. Nothing changed.")
        sys.exit(0)

servers[SERVER_NAME] = SERVER_ENTRY

# 3. Write to a temp file, then swap. A crash mid-write cannot leave a
#    half-written config behind.
tmp = CONFIG + '.tmp'
with open(tmp, 'w', encoding='utf-8') as f:
    json.dump(cfg, f, indent=2)
os.replace(tmp, CONFIG)

print(f"\nAdded '{SERVER_NAME}'. Total servers now: {len(servers)}")
print("Fully quit Claude Desktop (not just the window) and reopen it.")
