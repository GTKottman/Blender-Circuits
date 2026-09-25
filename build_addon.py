"""Package the Blender add-on as dist/blender_circuits.zip (install via Preferences > Add-ons > Install from Disk)."""

import os
import zipfile

ROOT = os.path.dirname(os.path.abspath(__file__))
SRC = os.path.join(ROOT, "blender_circuits")
OUT = os.path.join(ROOT, "dist", "blender_circuits.zip")


def main():
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with zipfile.ZipFile(OUT, "w", zipfile.ZIP_DEFLATED) as zf:
        for name in sorted(os.listdir(SRC)):
            if name.endswith((".py", ".toml")):
                zf.write(os.path.join(SRC, name), os.path.join("blender_circuits", name))
    print("wrote", OUT)


if __name__ == "__main__":
    main()
