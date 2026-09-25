#!/usr/bin/env python3
"""Render preview frames at several video times and tile them into one contact-sheet PNG.

Talks straight to the Circuit Lab bridge socket (same protocol the MCP server uses), so it needs to run on a
machine that can reach Blender (default 127.0.0.1:9877; override with BLENDER_CIRCUITS_HOST/PORT).

    python contact_sheet.py 1 4.5 9 14 --out review.png --width 640 --cols 2

Every frame is also saved individually (review_t1.0.png, ...). Pillow is optional: without it you get only
the individual frames.
"""

import argparse
import base64
import json
import os
import socket
import sys


def call(sock, buf, command, params):
    sock.sendall((json.dumps({"id": 1, "command": command, "params": params}) + "\n").encode())
    while b"\n" not in buf[0]:
        chunk = sock.recv(1 << 20)
        if not chunk:
            raise SystemExit("Blender closed the connection")
        buf[0] += chunk
    line, buf[0] = buf[0].split(b"\n", 1)
    resp = json.loads(line)
    if resp.get("status") != "ok":
        raise SystemExit("Blender error during %s: %s" % (command, resp.get("message")))
    return resp["result"]


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("times", nargs="+", type=float, help="video times in seconds")
    ap.add_argument("--out", default="contact_sheet.png")
    ap.add_argument("--width", type=int, default=640)
    ap.add_argument("--samples", type=int, default=8)
    ap.add_argument("--cols", type=int, default=0, help="columns (default: 2 for <=4 frames, else 3)")
    args = ap.parse_args()

    host = os.environ.get("BLENDER_CIRCUITS_HOST", "127.0.0.1")
    port = int(os.environ.get("BLENDER_CIRCUITS_PORT", "9877"))
    try:
        sock = socket.create_connection((host, port), timeout=600)
    except OSError as exc:
        raise SystemExit("Cannot reach the Circuit Lab bridge at %s:%d (%s). Start it in Blender first." % (host, port, exc))
    buf = [b""]
    os.makedirs(os.path.dirname(os.path.abspath(args.out)), exist_ok=True)
    stem, _ = os.path.splitext(args.out)
    files = []
    for t in args.times:
        res = call(sock, buf, "preview", {"time": t, "width": args.width, "samples": args.samples})
        path = "%s_t%.1f.png" % (stem, t)
        with open(path, "wb") as fh:
            fh.write(base64.b64decode(res["image_base64"]))
        files.append((t, path))
        print("frame", t, "->", path)
    sock.close()

    try:
        from PIL import Image, ImageDraw
    except ImportError:
        print("Pillow not installed; skipped the tiled sheet (pip install pillow).")
        return
    images = [(t, Image.open(p).convert("RGB")) for t, p in files]
    w, h = images[0][1].size
    cols = args.cols or (2 if len(images) <= 4 else 3)
    rows = (len(images) + cols - 1) // cols
    sheet = Image.new("RGB", (cols * w, rows * h), (20, 20, 20))
    for i, (t, im) in enumerate(images):
        x, y = (i % cols) * w, (i // cols) * h
        sheet.paste(im, (x, y))
        ImageDraw.Draw(sheet).text((x + 8, y + 6), "t = %.1f s" % t, fill=(255, 255, 0))
    sheet.save(args.out)
    print("contact sheet ->", args.out)


if __name__ == "__main__":
    sys.exit(main())
