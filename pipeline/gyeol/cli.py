"""명령줄 진입점: python -m gyeol.cli <command> --region <id>"""

from __future__ import annotations

import argparse
import json


def main(argv=None):
    ap = argparse.ArgumentParser(prog="gyeol")
    ap.add_argument("command", choices=["layers", "data", "scenarios", "demo", "xval", "cluster"])
    ap.add_argument("--region", default=None)
    ap.add_argument("--force", action="store_true")
    a = ap.parse_args(argv)
    from .config import params
    rid = a.region or params()["region"]["default"]
    if a.command == "layers":
        from .layers import build_layers
        print(json.dumps(build_layers(rid, a.force)["layers"], ensure_ascii=False, indent=1))
    elif a.command == "data":
        from .build import build_all
        build_all(rid, a.force)
    elif a.command == "scenarios":
        from .scenarios import run_all
        run_all()
    elif a.command == "demo":
        from .personality import build_demo
        build_demo(rid)
    elif a.command == "xval":
        from .export import export_xval
        export_xval(rid)
    elif a.command == "cluster":
        from .personality import build_demo
        build_demo(rid)


if __name__ == "__main__":
    main()
