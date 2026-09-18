"""Command line entry point: convert a file of route patterns, one per line."""

import argparse
import sys

from .converter import (
    RouteSyntaxError,
    django_to_express,
    django_to_flask,
    express_to_django,
    express_to_flask_rules,
    flask_to_django,
    flask_to_express,
)

_CONVERTERS = {
    ("flask", "express"): flask_to_express,
    ("express", "flask"): express_to_flask_rules,
    ("django", "express"): django_to_express,
    ("express", "django"): express_to_django,
    ("flask", "django"): flask_to_django,
    ("django", "flask"): django_to_flask,
}

_FORMATS = ("flask", "express", "django")

# flask and express can each only mean the other when --from is omitted;
# django is ambiguous with either, so it always needs an explicit --from.
_IMPLICIT_FROM = {"express": "flask", "flask": "express"}


def _iter_lines(handle):
    for lineno, raw in enumerate(handle, start=1):
        text = raw.rstrip("\n")
        stripped = text.strip()
        if not stripped or stripped.startswith("#"):
            continue
        yield lineno, text


def convert_stream(handle, convert):
    """Convert every non-blank, non-comment line from handle using convert.

    Returns (results, errors) rather than raising, so one bad line in
    a large route file doesn't stop the rest from being converted.
    convert may return either a single pattern or a list of patterns
    (express_to_flask_rules returns one rule per line, expanded per
    optional parameter), so a list result is flattened into results
    rather than appended as one entry.
    """
    results = []
    errors = []
    for lineno, text in _iter_lines(handle):
        try:
            converted = convert(text, line=lineno)
        except RouteSyntaxError as exc:
            errors.append(exc)
            continue
        if isinstance(converted, list):
            results.extend(converted)
        else:
            results.append(converted)
    return results, errors


def main(argv=None):
    parser = argparse.ArgumentParser(
        prog="routeconv",
        description="Convert route patterns between Flask/Werkzeug, Django and Express syntax.",
    )
    parser.add_argument(
        "--to",
        choices=_FORMATS,
        required=True,
        help="target format for the conversion",
    )
    parser.add_argument(
        "--from",
        dest="from_format",
        choices=_FORMATS,
        help="source format (default: inferred from --to for flask/express; "
        "required when --to is 'django')",
    )
    parser.add_argument(
        "path",
        nargs="?",
        help="file of route patterns, one per line (default: stdin)",
    )
    args = parser.parse_args(argv)

    from_format = args.from_format or _IMPLICIT_FROM.get(args.to)
    if from_format is None:
        parser.error(
            "--from is required when --to is 'django' (the source format is ambiguous)"
        )
    if from_format == args.to:
        parser.error("--from and --to must be different formats")
    convert = _CONVERTERS.get((from_format, args.to))
    if convert is None:
        parser.error(
            f"conversion from {from_format!r} to {args.to!r} is not supported yet"
        )

    if args.path:
        with open(args.path, encoding="utf-8") as handle:
            results, errors = convert_stream(handle, convert)
    else:
        results, errors = convert_stream(sys.stdin, convert)

    for line in results:
        print(line)

    source_name = args.path or "<stdin>"
    for err in errors:
        print(f"{source_name}:{err}", file=sys.stderr)

    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
