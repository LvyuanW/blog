#!/usr/bin/env bash
# Run on the server after pushing the reviewed main branch.
set -euo pipefail
repo_dir="${BLOG_REPO_DIR:-/opt/6yuan-blog}"
site_dir="${BLOG_SITE_DIR:-/var/www/6yuan}"
mkdir -p "$site_dir"
exec 9>"${site_dir}/.publish.lock"
flock -n 9 || { printf 'Another publication is running.\n' >&2; exit 1; }
cd "$repo_dir"
git fetch origin main
git merge --ff-only origin/main
python3 scripts/validate.py
python3 scripts/build.py
revision="$(git rev-parse --short HEAD)"
release="${site_dir}/releases/$(date -u +%Y%m%dT%H%M%SZ)-${revision}"
mkdir -p "$release"
cp -a dist/. "$release/"
chmod -R a+rX "$release"
next_link="${site_dir}/.current-${revision}-$$"
trap 'rm -f "$next_link"' EXIT
ln -s "$release" "$next_link"
mv -Tf "$next_link" "${site_dir}/current"
printf 'Published %s\n' "$release"
