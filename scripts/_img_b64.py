#!/usr/bin/env python3
import sys, io, base64
from PIL import Image
p = sys.argv[1]
maxpx = int(sys.argv[2]) if len(sys.argv) > 2 else 1000
im = Image.open(p)
im.thumbnail((maxpx, maxpx))
b = io.BytesIO()
im.convert("RGB").save(b, "JPEG", quality=80)
sys.stdout.write(base64.b64encode(b.getvalue()).decode())
