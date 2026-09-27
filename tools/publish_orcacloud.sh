#!/usr/bin/env bash
# Publishes one version on OrcaCloud with GitHub trusted publishing (OIDC):
# no token or secret, the repository must be connected to the plugin on
# OrcaCloud (Edit plugin > GitHub publishing). Runs inside a GitHub Actions
# job with `permissions: id-token: write`.
#
#   tools/publish_orcacloud.sh <version> <notes.md> <plugin file>
#
# OrcaCloud answers 201 when the version is published, 401 when this
# repository is not connected to exactly one plugin, and a version error when
# the version is not higher than the one already there.
set -euo pipefail
version="$1"
notes="$2"
file="$3"

oidc_token="$(curl -sS -H "Authorization: Bearer $ACTIONS_ID_TOKEN_REQUEST_TOKEN" \
  "$ACTIONS_ID_TOKEN_REQUEST_URL&audience=orcacloud" | jq -r .value)"
# at most 4000 bytes, cut on a character boundary (the notes have accents)
changelog="$(python3 -c 'import sys; print(open(sys.argv[1], encoding="utf-8").read().encode()[:4000].decode("utf-8", "ignore"))' "$notes")"
metadata="$(jq -cn --arg version "$version" --arg changelog "$changelog" \
  '{version: $version} + (if $changelog == "" then {} else {changelog: $changelog} end)')"
status="$(curl -sS -o response.json -w '%{http_code}' \
  -H "Authorization: Bearer $oidc_token" \
  -F "metadata=$metadata" -F "files=@$file" \
  https://api.orcaslicer.com/api/v1/plugin-publish/releases)"
echo "OrcaCloud answered $status:"
cat response.json
echo
[ "$status" = "201" ]
