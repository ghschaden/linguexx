"""Measuring the rendered page: ink, strokes, clearances, brace curvature.

Split out of runtests.py; the content is unchanged.  These render a PDF to
a grey raster and measure it, which is what makes a claim about a SHAPE --
the mirrored brace that CLAUDE.md remembers was found here, not in the
coordinates.
"""

import subprocess
from pathlib import Path

def _render_gray(pdf: Path, dpi: int):
    """The first page as (pixels, width, height): one byte per pixel, 0 = black.

    Everything else in this file reads the TEXT layer, which is blind to
    vector ink -- and a drawn brace is nothing but vector ink.  pdftoppm is
    already a hard requirement of the suite, and its raw PGM needs no image
    library to read.
    """
    out = subprocess.run(
        ["pdftoppm", "-gray", "-r", str(dpi), "-f", "1", "-l", "1", str(pdf)],
        capture_output=True, check=True,
    ).stdout
    # P5 header: magic, width, height, maxval, one whitespace byte, then data
    fields, pos = [], 2
    while len(fields) < 3:
        while out[pos:pos + 1].isspace():
            pos += 1
        if out[pos:pos + 1] == b"#":                    # comment to end of line
            pos = out.index(b"\n", pos) + 1
            continue
        end = pos
        while not out[end:end + 1].isspace():
            end += 1
        fields.append(int(out[pos:end]))
        pos = end
    w, h, _maxval = fields
    return out[pos + 1:], w, h


def brace_bulge(pdf: Path, x0, x1, y0, y1, dpi=300):
    """Which way the brace inside the given box (PDF points) curls.

    A brace decoration is not symmetric top-to-bottom about a vertical
    line: its middle tip protrudes to one side and its two ends to the
    other.  Which side the tip takes is the whole difference between "{"
    and "}", and it is invisible to any check that only measures where the
    ink IS -- the mirrored-brace bug of v0.13 sat at the right coordinates.

    Returns tip_x - ends_x in pixels: NEGATIVE for an opening "{" (tip to
    the left), POSITIVE for a closing "}".  Raises if the box holds no ink,
    which means the caller's coordinates missed the brace.
    """
    px, w, h = _render_gray(pdf, dpi)
    s = dpi / 72.0
    cx0, cx1 = max(0, int(x0 * s)), min(w, int(x1 * s) + 1)
    cy0, cy1 = max(0, int(y0 * s)), min(h, int(y1 * s) + 1)

    def centroid(y):
        base = y * w
        # a generous threshold on purpose: the brace is a hairline, thinner
        # than a pixel at any sane resolution, so most of it survives only
        # as anti-aliasing and a strict cut-off would drop the curve
        dark = [x for x in range(cx0, cx1) if px[base + x] < 224]
        return sum(dark) / len(dark) if dark else None

    rows = {y: c for y in range(cy0, cy1) if (c := centroid(y)) is not None}
    if not rows:
        raise AssertionError(
            f"no ink in the brace box ({x0:.1f},{y0:.1f})-({x1:.1f},{y1:.1f})")
    # A brace is TALLER than the text it braces -- the callers' band comes
    # from the row glyphs -- and its ENDS are exactly the part that sticks
    # out.  Cutting them off leaves the tip measured against the middle of
    # the curve rather than against the ends, which shrinks the very
    # difference this is looking for.  So follow the ink out of the band,
    # which stops by itself in the blank space above and below.
    for step, limit in ((-1, 0), (1, h - 1)):
        y = (min(rows) if step < 0 else max(rows)) + step
        while y != limit and (c := centroid(y)) is not None:
            rows[y] = c
            y += step
    ys = sorted(rows)
    if len(ys) < 8:
        raise AssertionError(f"only {len(ys)} inked rows: no brace here")
    # Measured against the ENDS rather than against the shaft, and by the
    # extreme rather than by an average over a band: a brace spends most of
    # its height on the shaft, so any mean is dominated by it and the
    # curl -- the whole signal -- is averaged away to a couple of pixels.
    ends = (rows[ys[0]] + rows[ys[1]] + rows[ys[-2]] + rows[ys[-1]]) / 4
    return max((rows[y] for y in ys), key=lambda c: abs(c - ends)) - ends


def glyph_ink(pdf: Path, w, dpi=600):
    r"""(ink height in pt, ink area in pt^2) of the glyphs inside word `w`.

    A word box is line-height and says nothing about the letters in it, so
    neither the SIZE nor the WEIGHT of a glyph shows up in the text layer:
    a bold lowercase "m" and a small-cap "M" occupy the same box and
    extract as the same word.  Both are exactly what \lpzg's modified
    labels are about, and both are plain in the rendered ink -- the height
    tells small caps from lowercase, the area tells bold from medium.

    Measured against a hard threshold rather than brace_bulge's generous
    one: a glyph is solid ink, not a hairline, and counting anti-aliasing
    would make the area depend on the resolution.
    """
    px, width, height = _render_gray(pdf, dpi)
    s = dpi / 72.0
    x0, x1 = max(0, int(w.x0 * s)), min(width, int(w.x1 * s) + 1)
    y0, y1 = max(0, int(w.y0 * s)), min(height, int(w.y1 * s) + 1)
    rows, dark = [], 0
    for y in range(y0, y1):
        base = y * width
        n = sum(1 for x in range(x0, x1) if px[base + x] < 128)
        if n:
            rows.append(y)
            dark += n
    if not rows:
        raise AssertionError(f"no ink in the box of {w!r}")
    return (max(rows) - min(rows) + 1) / s, dark / (s * s)


def stroke_width(pdf: Path, x0, x1, y0, y1, dpi=1200):
    """The typical horizontal ink run in a box, in points.

    For a brace's shaft -- which is near vertical over the stretch this is
    handed -- that run IS the stroke width, and a stroke width is the one
    thing a brace has that neither its position nor its curl records.  The
    median row is taken rather than the mean: the band may catch a row or
    two of the corner, where the curve turns and the horizontal run is
    longer than the pen.

    At 1200dpi one pixel is 0.06pt, so a pen of 0.4pt and one of 1.2pt are
    twenty pixels apart -- far outside anything anti-aliasing moves.
    """
    px, width, height = _render_gray(pdf, dpi)
    s = dpi / 72.0
    cx0, cx1 = max(0, int(x0 * s)), min(width, int(x1 * s) + 1)
    runs = []
    for y in range(max(0, int(y0 * s)), min(height, int(y1 * s) + 1)):
        base = y * width
        dark = [x for x in range(cx0, cx1) if px[base + x] < 160]
        if dark:
            runs.append((dark[-1] - dark[0] + 1) / s)
    if not runs:
        raise AssertionError(
            f"no ink in ({x0:.1f},{y0:.1f})-({x1:.1f},{y1:.1f})")
    runs.sort()
    return runs[len(runs) // 2]


def ink_clearance(pdf: Path, x0, x1, y0, y1, dpi=1200):
    """The narrowest gap, in points, between the first two runs of ink in
    a box -- scanned row by row, and the smallest gap any row shows.

    This is the measurement for "these two things do not touch", and it
    exists because nothing else in a PDF says so: TeX has no opinion about
    overlapping ink, so a judgment mark printed on top of a brace compiles
    clean, extracts clean, and is wrong only on the page.  Row-wise and
    minimum, because the two shapes approach each other at one height and
    the box average would hide it.
    """
    px, width, height = _render_gray(pdf, dpi)
    s = dpi / 72.0
    cx0, cx1 = max(0, int(x0 * s)), min(width, int(x1 * s) + 1)
    best = None
    for y in range(max(0, int(y0 * s)), min(height, int(y1 * s) + 1)):
        base = y * width
        dark = [x for x in range(cx0, cx1) if px[base + x] < 170]
        if not dark:
            continue
        runs = []
        for x in dark:
            if runs and x - runs[-1][-1] <= 3:
                runs[-1].append(x)
            else:
                runs.append([x])
        if len(runs) >= 2:
            gap = (runs[1][0] - runs[0][-1]) / s
            if best is None or gap < best:
                best = gap
    if best is None:
        raise AssertionError(
            f"no two runs of ink in ({x0:.1f},{y0:.1f})-({x1:.1f},{y1:.1f})")
    return best


def ink_bbox(pdf: Path, x0, y0, x1, y1, dpi=600, threshold=200):
    """(left, top, right, bottom) in PDF points of the ink inside a box.

    Where glyph_ink asks how big and how heavy a glyph is, this asks where
    it is -- and asks it of ink rather than of a text-layer box, so that a
    drawn brace and a period can be compared with each other at all.  The
    threshold sits between brace_bulge's generous 224 (a hairline survives
    mostly as anti-aliasing) and glyph_ink's strict 128: both things
    measured here have a solid core, and the edge pixels either way move
    the answer by less than the tolerances that read it.
    """
    px, width, height = _render_gray(pdf, dpi)
    s = dpi / 72.0
    cx0, cx1 = max(0, int(x0 * s)), min(width, int(x1 * s) + 1)
    cy0, cy1 = max(0, int(y0 * s)), min(height, int(y1 * s) + 1)
    xs, ys = [], []
    for y in range(cy0, cy1):
        base = y * width
        row = [x for x in range(cx0, cx1) if px[base + x] < threshold]
        if row:
            ys.append(y)
            xs += (row[0], row[-1])
    if not ys:
        raise AssertionError(
            f"no ink in ({x0:.1f},{y0:.1f})-({x1:.1f},{y1:.1f})")
    return min(xs) / s, min(ys) / s, max(xs) / s, max(ys) / s
