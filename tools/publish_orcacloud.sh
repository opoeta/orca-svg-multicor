#!/usr/bin/env bash
# Publishes one version on OrcaCloud with GitHub trusted publishing (OIDC):
# no token or secret, the repository must be connected to the plugin on
# OrcaCloud (Edit plugin > GitHub publishing). Runs inside a GitHub Actions
# job with `permissions: id-token: write`, started by a published release
# (.github/workflows/publish-orcacloud.yml).
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
# which run OrcaCloud sees: a few claims of the token, never the token itself
python3 -c '
import base64, json, sys
part = sys.argv[1].split(".")[1]
claims = json.loads(base64.urlsafe_b64decode(part + "=" * (-len(part) % 4)))
print({k: claims.get(k) for k in ("repository", "event_name", "ref", "workflow_ref")})
' "$oidc_token"
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
