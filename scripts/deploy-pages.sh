#!/usr/bin/env bash
# Deploy the publish job's Pages artifact to GitHub Pages, giving each
# deployment a name of its own.
#
#   scripts/deploy-pages.sh ARTIFACT_ID NAME
#
# ARTIFACT_ID is actions/upload-pages-artifact's artifact_id output, and NAME
# tells this publish apart from the run's other publish and from its earlier
# attempts (publish-pages.yml passes the artifact's name).
#
# This does what actions/deploy-pages does, through the same API, except for
# the deployment's name (its "build version", which is also its ID). The
# action always uses the commit the run started from, so a run's two
# publishes and every re-run of them share one name. Once a deployment has
# been cancelled, a new one under its name never starts: on 2026-11-10 a
# deployment stalled and was cancelled, and the re-run of the publish then sat
# without a status (docs/publish-incident-2026-11-10.md). Here the name also
# carries the run, NAME and the try.
#
# A try that has not succeeded within DEPLOY_TIMEOUT_SECONDS is cancelled,
# and one that ends in failure is left as it is; either way the deployment is
# made again under a new name, up to DEPLOY_ATTEMPTS tries in all. The status
# is read every DEPLOY_POLL_SECONDS, and DEPLOY_RETRY_DELAY_SECONDS is the
# pause before the second try (it doubles after each further failure).
# Writes page_url to $GITHUB_OUTPUT. The job needs the permissions pages:
# write and id-token: write, and gh needs GH_TOKEN.
set -euo pipefail
source "$(dirname "${BASH_SOURCE[0]}")/retry.sh"

artifact_id="$1"
name="$2"
api="repos/${GITHUB_REPOSITORY}/pages/deployments"
tries=0

# One try. Returns non-zero, rather than exiting, on any failure: retry runs
# it as a loop condition, where bash ignores `set -e`.
deploy() {
  tries=$(( tries + 1 ))
  local version="${GITHUB_SHA}-${GITHUB_RUN_ID}-${name}-${tries}"
  local oidc_token created id page_url status last=""
  # Pages checks that the deployment comes from this workflow run.
  oidc_token="$(curl -sSf --max-time 30 \
                  -H "Authorization: bearer ${ACTIONS_ID_TOKEN_REQUEST_TOKEN}" \
                  "${ACTIONS_ID_TOKEN_REQUEST_URL}" | jq -r .value)" || return 1
  echo "Creating Pages deployment ${version} from artifact ${artifact_id}"
  created="$(gh api -X POST "$api" -F artifact_id="$artifact_id" \
               -f pages_build_version="$version" -f oidc_token="$oidc_token")" || return 1
  id="$(jq -r .id <<<"$created")" || return 1
  page_url="$(jq -r .page_url <<<"$created")" || return 1
  local deadline=$(( SECONDS + DEPLOY_TIMEOUT_SECONDS ))
  while (( SECONDS < deadline )); do
    sleep "$DEPLOY_POLL_SECONDS"
    # A status that cannot be read is retried at the next poll, until the
    # deadline, as actions/deploy-pages does.
    status="$(gh api "$api/$id" --jq .status)" || status="(status not readable)"
    if [[ "$status" != "$last" ]]; then
      echo "Pages deployment ${id}: ${status:-(no status)}"
      last="$status"
    fi
    case "$status" in
      succeed)
        echo "page_url=${page_url}" >> "$GITHUB_OUTPUT"
        return 0 ;;
      deployment_failed|deployment_perms_error|deployment_content_failed|deployment_cancelled|deployment_lost)
        return 1 ;;
    esac
  done
  echo "::warning::Pages deployment ${id} did not finish within ${DEPLOY_TIMEOUT_SECONDS}s; cancelling it"
  gh api -X POST "$api/$id/cancel" > /dev/null \
    || echo "::warning::Could not cancel Pages deployment ${id}"
  return 1
}

retry "Deploying to GitHub Pages" "$DEPLOY_ATTEMPTS" "$DEPLOY_RETRY_DELAY_SECONDS" "" deploy
