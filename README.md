# routeconv

Converts URL route patterns between Flask/Werkzeug, Django and
Express-style syntax.

If you're porting routes between a Flask or Django backend and a
Node/Express one (or writing an OpenAPI spec by hand and need both),
you end up translating things like this by eye:

```
Flask:    /users/<int:id>/posts/<slug>
Express:  /users/:id(\d+)/posts/:slug
```

It's mechanical, but the syntaxes don't map 1:1. Flask and Django both
write a typed parameter as `<converter:name>`, but they ship different
converters (Django has no `float`, Flask has no `slug`) and even
converters both have use different regexes under the hood (Flask's
`uuid` is case-insensitive, Django's is lowercase-only). Express lets
you bolt on any regex, and has features (optional params, wildcards)
that neither of the others have. Getting a translation wrong produces
a route that silently matches the wrong thing, so this tool tries hard
to fail loudly and precisely instead of guessing.

## Usage

`--to` picks the output format. `--from` picks the input format; it
can be omitted when converting between `flask` and `express`, since
each one unambiguously implies the other, but it's required for
`django`, since a bracket-syntax pattern could be either Flask or
Django.

```
$ echo '/users/<int:id>/posts/<slug>' | python -m routeconv --to express
/users/:id(\d+)/posts/:slug

$ echo '/users/:id(\d+)/posts/:slug' | python -m routeconv --to flask
/users/<int:id>/posts/<slug>

$ echo '/users/<int:pk>' | python -m routeconv --to express --from django
/users/:pk([0-9]+)

$ echo '/users/:pk([0-9]+)' | python -m routeconv --to django --from express
/users/<int:pk>

$ echo '/users/<int:id>' | python -m routeconv --to django --from flask
/users/<int:id>
```

Flask and Django can also be converted directly into each other
without going through Express - this matters for `uuid`, since Flask
and Django both have a converter of that name but with slightly
different underlying regexes, so a direct conversion keeps it as
`uuid` on both sides instead of resolving it to a regex and looking
that regex back up.

Or convert a whole file of routes, one pattern per line (blank lines
and lines starting with `#` are skipped):

```
$ cat routes.txt
# public API
/health
/users/<int:id>
/files/<path:filepath>

$ python -m routeconv --to express routes.txt
/health
/users/:id(\d+)
/files/:filepath(.*)
```

## Error messages

Malformed or unconvertible patterns raise `RouteSyntaxError`, which
carries a line and column pointing at the exact problem, with a caret
and a hint where one is available:

```
$ echo '/users/<int:id/comments' | python -m routeconv --to express
routes.txt:line 1, column 8: unterminated parameter, expected a closing '>'
    /users/<int:id/comments
       ^
    hint: every '<' must be closed with '>'
```

```
$ echo '/files/:name(\d+)?' | python -m routeconv --to flask
routes.txt:line 1, column 18: optional parameters ('?') have no equivalent in Flask/Werkzeug
    /files/:name(\d+)?
                     ^
    hint: split this into two separate rules instead
```

When converting from a file, one bad line doesn't stop the rest -
every line is converted independently, valid output goes to stdout,
and every error goes to stderr with its own line number.

## Supported converters

| Flask       | Express regex constraint |
|-------------|---------------------------|
| `<name>`    | `:name` (no constraint)   |
| `<int:x>`   | `:x(\d+)`                 |
| `<float:x>` | `:x(\d+\.\d+)`            |
| `<uuid:x>`  | `:x([0-9a-fA-F]{8}-...)` |
| `<path:x>`  | `:x(.*)`                  |

| Django       | Express regex constraint |
|--------------|---------------------------|
| `<name>`     | `:name` (no constraint)   |
| `<int:x>`    | `:x([0-9]+)`              |
| `<slug:x>`   | `:x([-a-zA-Z0-9_]+)`      |
| `<uuid:x>`   | `:x([0-9a-f]{8}-...)`    |
| `<path:x>`   | `:x(.+)`                  |

Express wildcards (`*`), optional segments (`:x?`), and arbitrary
regex constraints with no matching converter on the other side all
raise an error rather than producing a route that doesn't actually
match what the original did.

## Running the tests

```
$ python -m unittest discover -s tests
```

## Status

Early skeleton. Flask/Werkzeug, Django and Express are supported for
conversion to and from each other - Flask and Express, and Django and
Express, go through a regex lookup; Flask and Django convert directly
by mapping converter names (see the source for exactly which
constraints and converters translate). Standard library only, no
dependencies.
