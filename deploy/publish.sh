#!/usr/bin/env bash
# Run on the server after pushing the reviewed main branch.
set -euo pipefail
publish() {
repo_dir="${BLOG_REPO_DIR:-/opt/6yuan-blog}"
site_dir="${BLOG_SITE_DIR:-/var/www/6yuan}"
mkdir -p "$site_dir"
exec 9>"${site_dir}/.publish.lock"
flock -n 9 || { printf 'Another publication is running.\n' >&2; exit 1; }
cd "$repo_dir"
script_before="$(git rev-parse HEAD:deploy/publish.sh)"
git fetch origin main
git merge --ff-only origin/main
# The whole function is parsed before fetching. If deployment code changed,
# restart it explicitly instead of continuing with the previous release's steps.
if [[ "$script_before" != "$(git rev-parse HEAD:deploy/publish.sh)" ]]; then
    flock -u 9
    exec bash "$repo_dir/deploy/publish.sh"
fi
python3 scripts/validate.py
export BLOG_PREVIOUS_MANIFEST="${site_dir}/current/.publication.json"
python3 scripts/build.py
python3 scripts/verify_seo.py
# Keep the ownership key and delivery history outside Git and release directories.
search_dir="${site_dir}/search"
mkdir -p "$search_dir"
chmod 700 "$search_dir"
python3 - "$search_dir/indexnow-key.txt" <<'PY'
import os, secrets, sys
from pathlib import Path
path = Path(sys.argv[1])
if not path.exists():
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(descriptor, 'w') as key:
        key.write(secrets.token_hex(16))
PY
indexnow_key="$(cat "$search_dir/indexnow-key.txt")"
cp "$search_dir/indexnow-key.txt" "dist/${indexnow_key}.txt"
revision="$(git rev-parse --short HEAD)"
release="${site_dir}/releases/$(date -u +%Y%m%dT%H%M%SZ)-${revision}"
mkdir -p "$release"
cp -a dist/. "$release/"
chmod -R a+rX "$release"
next_link="${site_dir}/.current-${revision}-$$"
trap 'rm -f "$next_link"' EXIT
ln -s "$release" "$next_link"
mv -Tf "$next_link" "${site_dir}/current"
python3 scripts/notify_search.py --manifest "${site_dir}/current/.publication.json" \
    --state "$search_dir/indexnow-state.json" --key-file "$search_dir/indexnow-key.txt" \
    || printf 'Published successfully; search notification is queued for retry.\n' >&2
printf 'Published %s\n' "$release"
}
publish "$@"
