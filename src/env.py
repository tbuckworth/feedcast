"""On/off switches set in the environment: workflow inputs such as RESEND_REPORT."""

import os


def env_flag(name: str) -> bool:
    """Whether environment variable `name` is on: "true", "1" or "yes", in any case.

    Surrounding spaces are ignored. Unset, empty or anything else is off.
    """
    return os.environ.get(name, "").strip().lower() in ("true", "1", "yes")
