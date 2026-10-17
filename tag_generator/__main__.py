import argparse
from pathlib import Path

from .engine import ROOT, InputError, build_tag
from .server import serve


def main():
    parser = argparse.ArgumentParser(description='EIE Hockey Tag-Generator')
    parser.add_argument('--name', help='Name auf dem Tag')
    parser.add_argument('--number', help='Nummer, 0–99 (führende Null bleibt erhalten)')
    parser.add_argument('--output', type=Path, default=ROOT / 'generated')
    parser.add_argument('--port', type=int, default=8765)
    parser.add_argument('--no-browser', action='store_true')
    args = parser.parse_args()
    if args.name is not None or args.number is not None:
        if args.name is None or args.number is None:
            parser.error('--name und --number müssen zusammen angegeben werden.')
        try:
            result = build_tag(args.name, args.number, args.output)
        except InputError as exc:
            parser.error(str(exc))
        print(result['project'])
        print(result['preview'])
    else:
        serve(args.port, not args.no_browser)


if __name__ == '__main__':
    main()
