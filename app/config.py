import os

ENV_FILE = os.path.join(os.path.dirname(os.path.dirname(__file__)), ".env")


def load_env(path=ENV_FILE):
    """Load KEY=value pairs from a .env file into the environment.

    Returns the names it set, which keeps the behaviour testable without
    inspecting os.environ from the outside.
    """
    if not os.path.isfile(path):
        return []

    applied = []
    try:
        with open(path, encoding="utf-8") as handle:
            lines = handle.readlines()
    except OSError:
        return []

    for line in lines:
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue

        key, _, value = line.partition("=")
        key = key.strip()
        if not key:
            continue

        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in ("'", '"'):
            value = value[1:-1]

        # A variable already set in the real environment takes precedence, so a
        # stale .env can never override what the host has configured.
        if key not in os.environ:
            os.environ[key] = value
            applied.append(key)

    return applied
