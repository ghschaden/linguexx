"""The assertion protocol, and the log helper the assertions share.

Split out of runtests.py; unchanged.  check() is deliberately pure -- it
returns a (ok, description) pair and accumulates nothing -- which is what
lets the assertion modules be independent of each other and of the runner.
"""

def warning_body(log: str, opening: str):
    """One \\PackageWarning from a .log, unwrapped into a single line.

    LaTeX breaks a warning across lines and prefixes the continuations with
    "(linguexx)", so nothing in a message longer than one line can be found
    by a plain substring test.
    """
    start = log.find(opening)
    if start < 0:
        return ""
    lines = []
    for line in log[start:].splitlines():
        if lines and not line.startswith("(linguexx)"):
            break
        lines.append(line.replace("(linguexx)", " "))
    return " ".join(" ".join(lines).split())


def check(cond, desc):
    return (bool(cond), desc)
