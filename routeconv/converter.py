"""Conversion between Flask/Werkzeug, Django and Express-style route patterns.

Flask and Django both write a typed parameter as <converter:name>
(converter optional, defaulting to "string" in Flask and "str" in
Django) - Django borrowed the syntax from Flask, but the two ship
different converters (Django has no "float", Flask has no "slug") and
some converters that exist in both use different regexes (uuid is
case-insensitive in Flask, lowercase-only in Django). Express writes a
parameter as :name, followed by an optional (regex) constraint. The
formats are close enough that most rules convert cleanly, but not
everything has an equivalent on the other side - Express wildcards
have no bracket-syntax counterpart, and arbitrary regex constraints
have no converter to map to. Those cases raise RouteSyntaxError rather
than guessing. Express optional params (:name?) are the one exception:
there's no single Flask rule that means "this segment might not be
there", but a pair of Flask rules (one with the segment, one without)
covers the same URLs, so express_to_flask_rules expands into those
instead of raising.

Flask and Django can also be converted directly into each other,
mapping converter names rather than routing through a regex - this is
more faithful than going via Express, since e.g. Flask's uuid and
Django's uuid are the same converter name with slightly different
underlying regexes, not a regex that has to be looked back up.
"""

import itertools

FLASK_CONVERTERS = {"string", "int", "float", "path", "uuid"}

_CONVERTER_TO_REGEX = {
    "int": r"\d+",
    "float": r"\d+\.\d+",
    "uuid": r"[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}",
    "path": r".*",
}

_REGEX_TO_CONVERTER = {regex: name for name, regex in _CONVERTER_TO_REGEX.items()}

DJANGO_CONVERTERS = {"str", "int", "slug", "uuid", "path"}

_DJANGO_CONVERTER_TO_REGEX = {
    "int": r"[0-9]+",
    "slug": r"[-a-zA-Z0-9_]+",
    "uuid": r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}",
    "path": r".+",
}

_DJANGO_REGEX_TO_CONVERTER = {
    regex: name for name, regex in _DJANGO_CONVERTER_TO_REGEX.items()
}

# Converters that mean the same thing in both frameworks, keyed by the
# Flask name. Flask's "float" and Django's "slug" have no counterpart
# and are deliberately left out; those raise RouteSyntaxError instead
# of dropping the constraint.
_FLASK_DJANGO_CONVERTER = {
    "string": "str",
    "int": "int",
    "path": "path",
    "uuid": "uuid",
}

_DJANGO_FLASK_CONVERTER = {name: flask for flask, name in _FLASK_DJANGO_CONVERTER.items()}


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


def _tokenize_express_with_optionals(pattern, line):
    """Parse an Express path into a list of ('lit', text) and
    ('param', name, converter, optional, slash_prefix) tokens.

    Unlike express_to_flask, a trailing '?' on a parameter does not
    raise - it's recorded on the token instead, along with whether the
    '/' immediately before the parameter belongs to it (so that '/'
    can be dropped too when the parameter is left out).
    """
    tokens = []
    literal = []
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
            literal.append(ch)
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

        optional = False
        if i < n and pattern[i] == "?":
            optional = True
            i += 1

        converter = None
        if regex is not None:
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

        slash_prefix = optional and bool(literal) and literal[-1] == "/"
        if slash_prefix:
            literal.pop()

        if literal:
            tokens.append(("lit", "".join(literal)))
            literal = []
        tokens.append(("param", name, converter, optional, slash_prefix))

    if literal:
        tokens.append(("lit", "".join(literal)))
    return tokens


def express_to_flask_rules(pattern, line=1):
    """Convert an Express-style path into every Flask/Werkzeug rule
    needed to cover the same URLs, expanding optional parameters
    (':name?') into one rule with the segment and one without it, e.g.
    '/users/:id?' becomes ['/users/<id>', '/users'].

    With more than one optional parameter this produces one rule per
    combination of present/absent, in the same order as itertools
    would enumerate them (all present first, all absent last).
    """
    tokens = _tokenize_express_with_optionals(pattern, line)
    optional_positions = [i for i, t in enumerate(tokens) if t[0] == "param" and t[3]]

    rules = []
    seen = set()
    for presence in itertools.product((True, False), repeat=len(optional_positions)):
        present = dict(zip(optional_positions, presence))
        parts = []
        for i, token in enumerate(tokens):
            if token[0] == "lit":
                parts.append(token[1])
                continue
            _, name, converter, optional, slash_prefix = token
            if optional and not present[i]:
                continue
            piece = f"<{converter}:{name}>" if converter else f"<{name}>"
            if optional and slash_prefix:
                piece = "/" + piece
            parts.append(piece)
        rule = "".join(parts) or "/"
        if rule not in seen:
            seen.add(rule)
            rules.append(rule)
    return rules


def flask_to_django(pattern, line=1):
    """Convert a Flask/Werkzeug rule, e.g. '/users/<int:id>', directly
    to a Django path pattern, e.g. '/users/<int:id>'.

    Maps converter names rather than routing through Express, so a
    converter that means the same thing in both frameworks (uuid,
    path, ...) round-trips as itself instead of as a regex lookup.
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

        django_converter = _FLASK_DJANGO_CONVERTER.get(converter)
        if django_converter is None:
            raise RouteSyntaxError(
                f"Flask converter {converter!r} has no Django equivalent",
                body_start + 1,
                pattern,
                line,
                hint="Django has no floating point converter; use 'int' or "
                "accept it as a string and parse it in the view",
            )
        out.append(f"<{name}>" if django_converter == "str" else f"<{django_converter}:{name}>")

    return "".join(out)


def django_to_flask(pattern, line=1):
    """Convert a Django path pattern, e.g. '/users/<int:pk>', directly
    to a Flask/Werkzeug rule, e.g. '/users/<int:pk>'.

    Maps converter names rather than routing through Express, for the
    same reason as flask_to_django.
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
            converter, name = "str", body
            name_offset = body_start

        if converter == "":
            raise RouteSyntaxError(
                "empty converter name before ':'", body_start + 1, pattern, line
            )
        if converter not in DJANGO_CONVERTERS:
            raise RouteSyntaxError(
                f"unknown converter {converter!r}",
                body_start + 1,
                pattern,
                line,
                hint="expected one of: " + ", ".join(sorted(DJANGO_CONVERTERS)),
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

        flask_converter = _DJANGO_FLASK_CONVERTER.get(converter)
        if flask_converter is None:
            raise RouteSyntaxError(
                f"Django converter {converter!r} has no Flask equivalent",
                body_start + 1,
                pattern,
                line,
                hint="Flask has no slug converter; use 'string' and validate "
                "the slug format in the view",
            )
        out.append(f"<{name}>" if flask_converter == "string" else f"<{flask_converter}:{name}>")

    return "".join(out)


def django_to_express(pattern, line=1):
    """Convert a Django path pattern, e.g. '/users/<int:pk>', to an
    Express-style path, e.g. '/users/:pk(\\d+)'.
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
            converter, name = "str", body
            name_offset = body_start

        if converter == "":
            raise RouteSyntaxError(
                "empty converter name before ':'", body_start + 1, pattern, line
            )
        if converter not in DJANGO_CONVERTERS:
            raise RouteSyntaxError(
                f"unknown converter {converter!r}",
                body_start + 1,
                pattern,
                line,
                hint="expected one of: " + ", ".join(sorted(DJANGO_CONVERTERS)),
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

        regex = _DJANGO_CONVERTER_TO_REGEX.get(converter)
        out.append(f":{name}({regex})" if regex else f":{name}")

    return "".join(out)


def express_to_django(pattern, line=1):
    """Convert an Express-style path, e.g. '/users/:pk(\\d+)', to a
    Django path pattern, e.g. '/users/<int:pk>'.
    """
    out = []
    i = 0
    n = len(pattern)
    while i < n:
        ch = pattern[i]
        if ch == "*":
            raise RouteSyntaxError(
                "wildcard segments ('*') have no equivalent in Django",
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
                "optional parameters ('?') have no equivalent in Django",
                i + 1,
                pattern,
                line,
                hint="split this into two separate rules instead",
            )

        if regex is None:
            out.append(f"<{name}>")
        else:
            converter = _DJANGO_REGEX_TO_CONVERTER.get(regex)
            if converter is None:
                raise RouteSyntaxError(
                    f"regex constraint {regex!r} has no matching Django converter",
                    regex_start + 2,
                    pattern,
                    line,
                    hint="supported constraints: "
                    + ", ".join(
                        f"{v!r} -> {k}" for k, v in _DJANGO_CONVERTER_TO_REGEX.items()
                    ),
                )
            out.append(f"<{converter}:{name}>")

    return "".join(out)
