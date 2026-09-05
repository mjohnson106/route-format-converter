"""Command line entry point: convert a file of route patterns, one per line."""

import argparse
import sys

from .converter import RouteSyntaxError, express_to_flask, flask_to_express

_CONVERTERS = {"express": flask_to_express, "flask": express_to_flask}


def _iter_lines(handle):
    for lineno, raw in enumerate(handle, start=1):
        text = raw.rstrip("\n")
        stripped = text.strip()
        if not stripped or stripped.startswith("#"):
            continue
        yield lineno, text


def convert_stream(handle, to):
    """Convert every non-blank, non-comment line from handle.

    Returns (results, errors) rather than raising, so one bad line in
    a large route file doesn't stop the rest from being converted.
    """
    convert = _CONVERTERS[to]
    results = []
    errors = []
    for lineno, text in _iter_lines(handle):
        try:
            results.append(convert(text, line=lineno))
        except RouteSyntaxError as exc:
            errors.append(exc)
    return results, errors


def main(argv=None):
    parser = argparse.ArgumentParser(
        prog="routeconv",
        description="Convert route patterns between Flask/Werkzeug and Express syntax.",
    )
    parser.add_argument(
        "--to",
        choices=sorted(_CONVERTERS),
        required=True,
        help="target format for the conversion",
    )
    parser.add_argument(
        "path",
        nargs="?",
        help="file of route patterns, one per line (default: stdin)",
    )
    args = parser.parse_args(argv)

    if args.path:
        with open(args.path, encoding="utf-8") as handle:
            results, errors = convert_stream(handle, args.to)
    else:
        results, errors = convert_stream(sys.stdin, args.to)

    for line in results:
        print(line)

    source_name = args.path or "<stdin>"
    for err in errors:
        print(f"{source_name}:{err}", file=sys.stderr)

    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
