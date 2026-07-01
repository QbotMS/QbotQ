#!/usr/bin/env python3
"""Podglad tras/wersji i retencja (przycinanie).
  route_versions_cli.py                          -> lista wszystkich tras
  route_versions_cli.py <route_id>               -> wersje jednej trasy
  route_versions_cli.py <route_id> --prune       -> podglad przyciecia (keep=3)
  route_versions_cli.py <route_id> --prune --keep 3 --confirm  -> realne przyciecie
"""
from __future__ import annotations
import argparse, json, os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from qbot3.routes.route_versions import list_all_routes, list_route_versions, prune_route_versions


def main() -> None:
    ap = argparse.ArgumentParser(description="Podglad tras/wersji i retencja.")
    ap.add_argument("route_id", nargs="?", default=None)
    ap.add_argument("--prune", action="store_true", help="Przytnij do N najnowszych wersji.")
    ap.add_argument("--keep", type=int, default=3, help="Ile najnowszych wersji zostawic (domyslnie 3).")
    ap.add_argument("--confirm", action="store_true", help="Wykonaj realne przyciecie (domyslnie podglad).")
    args = ap.parse_args()

    if args.prune:
        if not args.route_id:
            print(json.dumps({"status": "ERROR", "error": "Podaj route_id do przyciecia."}, ensure_ascii=False))
            return
        out = prune_route_versions(args.route_id, keep=args.keep, confirm=args.confirm)
    elif args.route_id:
        out = list_route_versions(args.route_id)
    else:
        out = list_all_routes()
    print(json.dumps(out, ensure_ascii=False, indent=2, default=str))


if __name__ == "__main__":
    main()
