import argparse
import sys

from app.collect import register


def main() -> int:
    parser = argparse.ArgumentParser(prog="glow")
    sub = parser.add_subparsers(dest="command", required=True)
    reg = sub.add_parser("register")
    reg.add_argument("mdl_id")
    serve = sub.add_parser("serve")
    serve.add_argument("--host", default="0.0.0.0")
    serve.add_argument("--port", type=int, default=8000)
    args = parser.parse_args()
    if args.command == "serve":
        from app.web import serve as serve_web

        serve_web(args.host, args.port)
        return 0
    try:
        result = register(args.mdl_id)
    except ValueError as exc:
        print(exc, file=sys.stderr)
        return 1
    if result.status == "collected":
        print(f"{result.mdl_id} collected person_id={result.person_id} works={result.works}")
        return 0
    print(f"{result.mdl_id} failed person_id={result.person_id}")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
