"""Synthetic signature specimens for the demo accounts. Never a real person's signature: the strokes come from a random
walk seeded by the name, so one name always draws the same specimen and no specimen needs to be stored in git.

The specimen is only the look of a signature. What proves it is the electronic signature behind it: the password at
that moment, the stored consent, the content hash and the verification code (app/signing.py)."""

from functools import lru_cache
import hashlib
from io import BytesIO
import random

from PIL import Image, ImageDraw

INK = (28, 40, 110, 255)  # dark blue, like a ballpoint pen
SIZE, SCALE = (360, 120), 4


def _spline(points, steps=14):
    """Catmull-Rom through the control points, so the pen moves in curves instead of corners."""
    padded = [points[0]] + points + [points[-1]]
    curve = []
    for i in range(1, len(padded) - 2):
        (x0, y0), (x1, y1), (x2, y2), (x3, y3) = padded[i - 1:i + 3]
        for step in range(steps):
            t = step / steps
            t2, t3 = t * t, t * t * t
            curve.append((0.5 * (2 * x1 + (-x0 + x2) * t + (2 * x0 - 5 * x1 + 4 * x2 - x3) * t2 + (-x0 + 3 * x1 - 3 * x2 + x3) * t3),
                          0.5 * (2 * y1 + (-y0 + y2) * t + (2 * y0 - 5 * y1 + 4 * y2 - y3) * t2 + (-y0 + 3 * y1 - 3 * y2 + y3) * t3)))
    curve.append(points[-1])
    return curve


def _strokes(name, rng):
    """One stroke per word: a looped capital, rounded humps and the odd tall loop for the remaining letters, then a
    flourish that swings back under the name. A forward slant makes it read as handwriting."""
    strokes, x, baseline, mid = [], 20.0, 80.0, 62.0
    slant = rng.uniform(0.18, 0.34)
    for word in name.split()[:2]:
        top = rng.uniform(14, 26)
        width = rng.uniform(14, 20)
        stroke = [(x, baseline + 4), (x + 3, top), (x + width, top + rng.uniform(6, 14)),
                  (x + width * 0.6, baseline - 14), (x + 2, baseline - 6), (x + width + 6, mid + 2)]
        x += width + 8
        for _ in range(max(2, min(len(word) - 1, 5))):
            kind = rng.random()
            if kind < 0.6:    # a rounded hump, like n or m
                stroke += [(x + 2, mid - rng.uniform(2, 6)), (x + 6, mid - rng.uniform(4, 8)), (x + 9, baseline - 2)]
                x += rng.uniform(10, 13)
            elif kind < 0.85:  # a tall loop, like l or h
                stroke += [(x + 5, top + rng.uniform(8, 18)), (x + 1, mid), (x + 7, baseline - 1)]
                x += rng.uniform(9, 12)
            else:              # a dip below the line, like g or y
                stroke += [(x + 4, mid), (x + 6, baseline + rng.uniform(14, 20)), (x + 2, baseline + 6), (x + 10, mid + 4)]
                x += rng.uniform(11, 14)
        strokes.append(stroke)
        x += rng.uniform(10, 18)
    end = strokes[-1][-1]
    strokes[-1] += [(end[0] + 14, mid - rng.uniform(10, 20)), (end[0] + 8, baseline + 12),
                    (x * 0.5, baseline + rng.uniform(14, 20)), (14, baseline + rng.uniform(6, 12))]
    return [[(px + (baseline - py) * slant, py) for px, py in stroke] for stroke in strokes]


@lru_cache(maxsize=None)
def synthetic_specimen(name):
    """PNG bytes of a made-up signature for `name`, transparent background, about 360x120 px."""
    rng = random.Random(int.from_bytes(hashlib.sha256(name.encode('utf-8')).digest()[:8], 'big'))
    strokes = [_spline(stroke) for stroke in _strokes(name, rng)]
    xs = [x for stroke in strokes for x, _ in stroke]
    ys = [y for stroke in strokes for _, y in stroke]
    left, top, right, bottom = min(xs) - 6, min(ys) - 6, max(xs) + 6, max(ys) + 6
    fit = min(SIZE[0] / (right - left), SIZE[1] / (bottom - top))
    canvas = Image.new('RGBA', (SIZE[0] * SCALE, SIZE[1] * SCALE), (255, 255, 255, 0))
    pen = ImageDraw.Draw(canvas)
    offset_x = (SIZE[0] - (right - left) * fit) / 2
    offset_y = (SIZE[1] - (bottom - top) * fit) / 2
    width = round(2.4 * SCALE)
    for stroke in strokes:
        line = [((x - left) * fit * SCALE + offset_x * SCALE, (y - top) * fit * SCALE + offset_y * SCALE) for x, y in stroke]
        pen.line(line, fill=INK, width=width, joint='curve')
        for cx, cy in (line[0], line[-1]):
            pen.ellipse((cx - width / 2, cy - width / 2, cx + width / 2, cy + width / 2), fill=INK)
    output = BytesIO()
    canvas.resize(SIZE, Image.LANCZOS).save(output, format='PNG', optimize=True)
    return output.getvalue()
