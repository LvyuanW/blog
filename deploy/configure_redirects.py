#!/usr/bin/env python3
"""One-time, idempotent route migration preserving Certbot's live TLS configuration."""
from datetime import datetime, timezone
from pathlib import Path
import subprocess

path = Path('/etc/nginx/sites-available/6yuan-blog')
original = path.read_text()
marker = '    location / { try_files $uri $uri/ =404; }'
redirects = '\n'.join('    location = ' + source + ' { return 301 https://blog.wanglvyuan.com/$is_args$args; }'
                      for source in ['/articles', '/articles/', '/articles/index.html'])
if redirects not in original:
    if original.count(marker) != 1 or 'location = /articles' in original:
        raise SystemExit('Unexpected Nginx configuration; review routes before migration.')
    backup = path.with_name(path.name + '.backup-' + datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ'))
    backup.write_text(original)
    path.write_text(original.replace(marker, redirects + '\n' + marker))
    try:
        subprocess.run(['nginx', '-t'], check=True)
        subprocess.run(['systemctl', 'reload', 'nginx'], check=True)
    except Exception:
        path.write_text(original)
        subprocess.run(['nginx', '-t'], check=True)
        subprocess.run(['systemctl', 'reload', 'nginx'], check=True)
        raise
    print('Canonical redirects installed; existing TLS settings preserved.')
else:
    print('Canonical redirects already configured.')
