import re

import pytest

_REF = re.compile(r"\$\{([A-Za-z_][A-Za-z0-9_]*)\}|\$([A-Za-z_][A-Za-z0-9_]*)")


def _envsubst(text, env):
    """GNU envsubst: $VAR / ${VAR} -> env value or empty; any other $ is literal."""
    out, i = [], 0
    while i < len(text):
        if text[i] == "$":
            m = _REF.match(text, i)
            if m:
                out.append(env.get(m.group(1) or m.group(2), ""))
                i = m.end()
                continue
            out.append("$")
            i += 1
            continue
        out.append(text[i])
        i += 1
    return "".join(out)


@pytest.fixture
def envsubst():
    return _envsubst
