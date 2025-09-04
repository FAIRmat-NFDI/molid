from __future__ import annotations
import re
from collections import Counter

_elem = re.compile(r"([A-Z][a-z]?)(\d*)")

def parse_formula(s: str) -> Counter:
    c = Counter()
    for el, n in _elem.findall(s.replace(" ", "")):
        c[el] += int(n or 1)
    return c

def canonicalize_formula(s: str) -> str:
    c = parse_formula(s)
    elems = sorted(c)  # alphabetical by default
    # Hill system: if C present, order C, H, then alphabetical others
    if "C" in c:
        ordered = ["C"] + (["H"] if "H" in c else []) + [e for e in elems if e not in ("C","H")]
    else:
        ordered = elems
    return "".join(f"{e}{c[e] if c[e] != 1 else ''}" for e in ordered)
