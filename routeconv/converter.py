"""Conversion between Flask/Werkzeug and Express-style route patterns.

Flask writes a typed parameter as <converter:name> (converter optional,
defaults to "string"). Express writes it as :name, followed by an
optional (regex) constraint. The two are close enough that most rules
convert cleanly, but not everything has an equivalent on the other
side - Express wildcards and optional params, for instance, have no
Flask counterpart, and arbitrary regex constraints have no Flask
converter to map to. Those cases raise RouteSyntaxError rather than
guessing.
"""

FLASK_CONVERTERS = {"string", "int", "float", "path", "uuid"}

_CONVERTER_TO_REGEX = {
    "int": r"\d+",
    "float": r"\d+\.\d+",
    "uuid": r"[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}",
    "path": r".*",
}

_REGEX_TO_CONVERTER = {regex: name for name, regex in _CONVERTER_TO_REGEX.items()}


class RouteSyntaxError(Exception):
    """A route pattern could not be parsed or converted.

    Carries the column (and, for multi-line input, the line) where
    the problem was found, so callers can print a caret-pointed
    message instead of just a description.
    """

    def __init__(self, message, column, source, line=1, hint=None):
        self.message = message
        self.column = column
        self.source = source
        self.line = line
        self.hint = hint
        super().__init__(message)

    def __str__(self):
        pointer = " " * (self.column - 1) + "^"
        parts = [
            f"line {self.line}, column {self.column}: {self.message}",
            f"    {self.source}",
            f"    {pointer}",
        ]
        if self.hint:
            parts.append(f"    hint: {self.hint}")
        return "\n".join(parts)


def _is_name_char(ch):
    return ch.isalnum() or ch == "_"


def flask_to_express(pattern, line=1):
    """Convert a Flask/Werkzeug rule, e.g. '/users/<int:id>', to an
    Express-style path, e.g. '/users/:id(\\d+)'.
    """
    out = []
    i = 0
    n = len(pattern)
    while i < n:
        ch = pattern[i]
        if ch == ">":
            raise RouteSyntaxError(
                "unexpected '>' with no matching '<'", i + 1, pattern, line
            )
        if ch != "<":
            out.append(ch)
            i += 1
            continue

        start = i
        i += 1
        body_start = i
        while i < n and pattern[i] != ">":
            i += 1
        if i >= n:
            raise RouteSyntaxError(
                "unterminated parameter, expected a closing '>'",
                start + 1,
                pattern,
                line,
                hint="every '<' must be closed with '>'",
            )
        body = pattern[body_start:i]
        i += 1  # skip '>'

        first_colon = body.find(":")
        second_colon = body.find(":", first_colon + 1) if first_colon != -1 else -1
        if second_colon != -1:
            raise RouteSyntaxError(
                "too many ':' in parameter, expected '<converter:name>' or '<name>'",
                body_start + second_colon + 1,
                pattern,
                line,
            )

        if first_colon != -1:
            converter, name = body[:first_colon], body[first_colon + 1 :]
            name_offset = body_start + first_colon + 1
        else:
            converter, name = "string", body
            name_offset = body_start

        if converter == "":
            raise RouteSyntaxError(
                "empty converter name before ':'", body_start + 1, pattern, line
            )
        if converter not in FLASK_CONVERTERS:
            raise RouteSyntaxError(
                f"unknown converter {converter!r}",
                body_start + 1,
                pattern,
                line,
                hint="expected one of: " + ", ".join(sorted(FLASK_CONVERTERS)),
            )
        if name == "":
            raise RouteSyntaxError(
                "empty parameter name", name_offset + 1, pattern, line
            )
        for offset, nch in enumerate(name):
            if not _is_name_char(nch):
                raise RouteSyntaxError(
                    f"invalid character {nch!r} in parameter name",
                    name_offset + offset + 1,
                    pattern,
                    line,
                    hint="parameter names may only contain letters, digits and '_'",
                )

        regex = _CONVERTER_TO_REGEX.get(converter)
        out.append(f":{name}({regex})" if regex else f":{name}")

    return "".join(out)


def express_to_flask(pattern, line=1):
    """Convert an Express-style path, e.g. '/users/:id(\\d+)', to a
    Flask/Werkzeug rule, e.g. '/users/<int:id>'.
    """
    out = []
    i = 0
    n = len(pattern)
    while i < n:
        ch = pattern[i]
        if ch == "*":
            raise RouteSyntaxError(
                "wildcard segments ('*') have no equivalent in Flask/Werkzeug",
                i + 1,
                pattern,
                line,
                hint="use a '<path:...>' converter and adjust the view manually",
            )
        if ch != ":":
            out.append(ch)
            i += 1
            continue

        start = i
        i += 1
        name_start = i
        while i < n and _is_name_char(pattern[i]):
            i += 1
        name = pattern[name_start:i]
        if name == "":
            raise RouteSyntaxError(
                "expected a parameter name after ':'", start + 1, pattern, line
            )

        regex = None
        regex_start = None
        if i < n and pattern[i] == "(":
            regex_start = i
            depth = 0
            while i < n:
                if pattern[i] == "\\":
                    i += 2
                    continue
                if pattern[i] == "(":
                    depth += 1
                elif pattern[i] == ")":
                    depth -= 1
                    if depth == 0:
                        i += 1
                        break
                i += 1
            else:
                raise RouteSyntaxError(
                    "unterminated regex constraint, expected a closing ')'",
                    regex_start + 1,
                    pattern,
                    line,
                )
            regex = pattern[regex_start + 1 : i - 1]

        if i < n and pattern[i] == "?":
            raise RouteSyntaxError(
                "optional parameters ('?') have no equivalent in Flask/Werkzeug",
                i + 1,
                pattern,
                line,
                hint="split this into two separate rules instead",
            )

        if regex is None:
            out.append(f"<{name}>")
        else:
            converter = _REGEX_TO_CONVERTER.get(regex)
            if converter is None:
                raise RouteSyntaxError(
                    f"regex constraint {regex!r} has no matching Flask converter",
                    regex_start + 2,
                    pattern,
                    line,
                    hint="supported constraints: "
                    + ", ".join(f"{v!r} -> {k}" for k, v in _CONVERTER_TO_REGEX.items()),
                )
            out.append(f"<{converter}:{name}>")

    return "".join(out)
