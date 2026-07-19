#!/usr/bin/env python3
"""Analyze an uncompressed tagged PDF: print the structure tree and
report any text shown outside marked content (untagged 'real content')."""
import re, sys, zlib
from collections import defaultdict

data = open(sys.argv[1], "rb").read()

# ---- collect objects ----
objs = {}
for m in re.finditer(rb"(\d+) 0 obj(.*?)endobj", data, re.S):
    objs[int(m.group(1))] = m.group(2)

def dictbody(b):
    m = re.search(rb"<<(.*)>>", b, re.S)
    return m.group(1) if m else b

# ---- structure tree ----
def sval(b, key):
    m = re.search(rb"/" + key + rb"\s*/([A-Za-z0-9#]+)", b)
    return m.group(1).decode() if m else None

def kids(b):
    # /K can be: int (MCID), ref, array of ints / refs / MCR dicts
    m = re.search(rb"/K\s*(\[(?:[^\[\]]|\[[^\]]*\])*\]|\d+\s+0\s+R|\d+)", b)
    if not m:
        return []
    s = m.group(1)
    out = []
    # MCR dicts: <</Type /MCR /Pg N 0 R /MCID k>>
    for r in re.finditer(rb"<<[^>]*?/MCID\s+(\d+)[^>]*?>>", s):
        out.append(("mcid", int(r.group(1))))
    s2 = re.sub(rb"<<[^>]*?>>", b"", s)          # drop dicts (incl. their /Pg refs)
    for r in re.finditer(rb"(\d+)\s+0\s+R", s2):
        out.append(("ref", int(r.group(1))))
    s3 = re.sub(rb"\d+\s+0\s+R", b"", s2)
    for r in re.finditer(rb"(?:^|[\[\s])(\d+)(?=[\s\]]|$)", s3):
        out.append(("mcid", int(r.group(1))))
    return out

root = None
# find the /StructTreeRoot reference wherever it appears uncompressed
mroot = re.search(rb"/StructTreeRoot\s+(\d+)\s+0\s+R", data)
if mroot and int(mroot.group(1)) in objs:
    root = int(mroot.group(1))
print("StructTreeRoot obj:", root)
if root is None:
    if b"/ObjStm" in data:
        print("  NOTE: this PDF is compressed (objects live in object "
              "streams), so the structure tree cannot be read from the "
              "raw bytes.  Recompile with \\DocumentMetadata{uncompress,...} "
              "to inspect it.  (The content-stream check below still works.)")
    else:
        print("  NOTE: no /StructTreeRoot found - tagging may be off, or "
              "this build produced no structure tree.")

def walk(n, depth, seen):
    if n in seen:
        print("  " * depth + f"[CYCLE {n}]"); return
    seen.add(n)
    b = objs.get(n, b"")
    s = sval(b, b"S") or ("STRUCTROOT" if n == root else "?")
    extras = []
    for key in (b"Alt", b"ActualText", b"Lang"):
        if b"/" + key in b:
            extras.append(key.decode())
    print("  " * depth + f"{s} (obj {n})" + (f" [{','.join(extras)}]" if extras else ""))
    for kind, v in kids(b):
        if kind == "ref":
            walk(v, depth + 1, seen)
        else:
            print("  " * (depth + 1) + f"MCID {v}")

walk(root, 0, set())

# ---- content stream: text outside BDC/EMC ----
print("\n=== content stream check ===")
streams = re.findall(rb"stream\r?\n(.*?)\r?\nendstream", data, re.S)
untagged, artifacts, tagged = 0, 0, 0
samples = []
for st in streams:
    try:
        st = zlib.decompress(st)
    except Exception:
        pass
    if b"BT" not in st:
        continue
    depth_mc, in_art = 0, 0
    stack = []
    for tok in re.finditer(rb"(/[A-Za-z][A-Za-z0-9]*\s*(?:<<[^>]*>>)?\s*(?:BDC|BMC))|(EMC)|(\[[^\]]*\]\s*TJ|\([^)]*\)\s*Tj)", st):
        if tok.group(1):
            stack.append(b"art" if tok.group(1).startswith(b"/Artifact") else b"mc")
        elif tok.group(2):
            if stack:
                stack.pop()
        else:
            if b"art" in stack:
                artifacts += 1
            elif stack:
                tagged += 1
            else:
                untagged += 1
                if len(samples) < 8:
                    samples.append(tok.group(3)[:70])
print(f"text ops: tagged={tagged} artifact={artifacts} UNTAGGED={untagged}")
for s in samples:
    print("  untagged sample:", s)
