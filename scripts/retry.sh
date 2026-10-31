# Sourced by the CI scripts that retry a step after a transient outside
# failure: a stalled apt mirror, a push GitHub refuses.
#
#   retry WHAT ATTEMPTS PAUSE BETWEEN COMMAND...
#
# Runs COMMAND until it succeeds, at most ATTEMPTS times. After each failure
# it prints a ::warning naming WHAT, sleeps PAUSE seconds (doubling the pause
# each time), then runs BETWEEN, a command, unless it is "". When the attempts
# run out it prints an ::error and returns 1.
retry() {
  # Prefixed: bash locals are visible to COMMAND and BETWEEN, so a plain name
  # such as "n" would shadow the caller's own variable of that name.
  local retry_what="$1" retry_attempts="$2" retry_pause="$3" retry_between="$4"
  shift 4
  local retry_n=1
  until "$@"; do
    if (( retry_n >= retry_attempts )); then
      echo "::error::${retry_what} failed ${retry_attempts} times; giving up"
      return 1
    fi
    echo "::warning::${retry_what} failed (attempt ${retry_n} of ${retry_attempts}); retrying in ${retry_pause}s"
    sleep "$retry_pause"
    retry_pause=$(( retry_pause * 2 ))
    retry_n=$(( retry_n + 1 ))
    if [[ -n "$retry_between" ]]; then "$retry_between"; fi
  done
}
