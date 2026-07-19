#!/usr/bin/env python3
"""Dump the accessibility structure of the recon PDF: how the sample formula
is tagged, whether MathML / an associated file / Alt / ActualText is attached,
and what raw text the Formula carries. Reads recon.pdf (uncompressed)."""
import re, sys, zlib

raw = open("recon.pdf", "rb").read()

def objs():
    d = {}
    for m in re.finditer(rb"(\d+) 0 obj\b(.*?)\bendobj", raw, re.S):
        d[int(m.group(1))] = m.group(2)
    return d
O = objs()

print("=== structure elements (tag -> count) ===")
from collections import Counter
tags = Counter(m.group(1).decode() for m in re.finditer(rb"/S\s*/(\w+)", raw))
for k, v in sorted(tags.items()):
    print(f"  {k}: {v}")

print("\n=== the Formula struct element(s), full dict ===")
for n, b in O.items():
    if b"/StructElem" in b and b"/Formula" in b:
        print(f"  obj {n}: {b.strip().decode('latin1')[:500]}")

print("\n=== Alt / ActualText / E / AF anywhere ===")
for key in (b"Alt", b"ActualText", b"/E ", b"/AF"):
    hits = re.findall(rb"/%s\s*(\([^)]*\)|<[0-9A-Fa-f]+>|\[[^\]]*\]|\d+ 0 R)" % key.strip(b"/ "), raw)
    print(f"  /{key.strip(b'/ ').decode()}: {len(hits)} occurrence(s)"
          + (f" -> {hits[0][:80]}" if hits else ""))

print("\n=== associated files / MathML streams present? ===")
print("  /AF present:", b"/AF" in raw)
print("  MathML (<math) in any stream:", b"<math" in raw or b"application/mathml" in raw)
print("  /Subtype /application#2Fmathml or AFRelationship:", b"AFRelationship" in raw)

print("\n=== reading order text of the sample line (struct dump proxy) ===")
# find the mc text runs in the first content stream
for m in re.finditer(rb"stream\r?\n(.*?)\r?\nendstream", raw, re.S):
    st = m.group(1)
    try: st = zlib.decompress(st)
    except Exception: pass
    if b"BT" in st and (b"the cat" in st or b"saw" in st):
        runs = re.findall(rb"\((.*?)\)\s*Tj|\[(.*?)\]\s*TJ", st)
        txt = []
        for a, bb in runs:
            s = a if a else bb
            s = re.sub(rb"<[0-9A-Fa-f]+>", b"", s)
            txt.append(s.decode("latin1"))
        print("  ", " | ".join(t for t in txt if t.strip())[:200])
        break


print("\n=== associated file (/AF) contents = the MathML a reader voices ===")
# find /Filespec objects and the embedded stream they point to
for n, b in O.items():
    if b"/Filespec" in b or b"/EmbeddedFile" in b or b"AFRelationship" in b:
        print(f"  -- Filespec/EF obj {n}: {b.strip().decode('latin1')[:300]}")
# dump any stream whose bytes look like MathML
import zlib as _z
for m in re.finditer(rb"(\d+) 0 obj\b(.*?)stream\r?\n(.*?)\r?\nendstream", raw, re.S):
    body = m.group(3)
    dec = body
    try: dec = _z.decompress(body)
    except Exception: pass
    if b"<math" in dec or b"mtable" in dec or b"mrow" in dec or b"mfenced" in dec:
        print(f"  -- MathML stream in obj {m.group(1).decode()} ({len(dec)} bytes):")
        print("     " + dec.decode("utf-8", "replace")[:900].replace("\n", "\n     "))
