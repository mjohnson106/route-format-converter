# routeconv

Converts URL route patterns between Flask/Werkzeug syntax and
Express-style syntax.

If you're porting routes between a Flask backend and a Node/Express
one (or writing an OpenAPI spec by hand and need both), you end up
translating things like this by eye:

```
Flask:    /users/<int:id>/posts/<slug>
Express:  /users/:id(\d+)/posts/:slug
```

It's mechanical, but the two syntaxes don't map 1:1 - Flask has a
fixed set of typed converters (`int`, `float`, `uuid`, `path`,
`string`), Express lets you bolt on any regex, and Express has
features (optional params, wildcards) that Flask just doesn't have.
Getting that translation wrong produces a route that silently matches
the wrong thing, so this tool tries hard to fail loudly and precisely
instead of guessing.

## Usage

```
$ echo '/users/<int:id>/posts/<slug>' | python -m routeconv --to express
/users/:id(\d+)/posts/:slug

$ echo '/users/:id(\d+)/posts/:slug' | python -m routeconv --to flask
/users/<int:id>/posts/<slug>
```

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

Express wildcards (`*`), optional segments (`:x?`), and arbitrary
regex constraints with no Flask converter equivalent all raise an
error rather than producing a route that doesn't actually match what
the original did.

## Running the tests

```
$ python -m unittest discover -s tests
```

## Status

Early skeleton. Only Flask/Werkzeug and Express are supported (see
the source for exactly which constraints translate). Standard
library only, no dependencies.
