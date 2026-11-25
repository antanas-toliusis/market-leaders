#!/bin/bash
# Headless smoke test: serves the repo locally, loads the page with tests/headless_probe.js
# appended, and prints the probe's JSON (written into <pre id="probe">). Charts are not
# drawn headless (no animation frames), so chart checks run in a real browser instead.
set -e
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
TMP="$(mktemp -d)"
cp "$ROOT/index.html" "$ROOT/data.json" "$ROOT/weekly.json" "$TMP/"
python3 - "$TMP/index.html" "$ROOT/tests/headless_probe.js" <<'EOF'
import sys
page, probe = sys.argv[1], open(sys.argv[2]).read()
h = open(page).read().replace('</body>', '<script>' + probe + '</script></body>')
open(page, 'w').write(h)
EOF
cd "$TMP"
python3 -m http.server 8790 >/dev/null 2>&1 &
SRV=$!
trap 'kill $SRV 2>/dev/null; rm -rf "$TMP"' EXIT
sleep 1
timeout 90 google-chrome --headless=new --no-sandbox --disable-gpu --virtual-time-budget=30000 \
  --dump-dom "http://localhost:8790/index.html" 2>/dev/null \
  | python3 -c "import sys,re,html;m=re.search(r'<pre id=\"probe\">(.*?)</pre>',sys.stdin.read(),re.S);print(html.unescape(m.group(1)) if m else 'NO PROBE OUTPUT')"
