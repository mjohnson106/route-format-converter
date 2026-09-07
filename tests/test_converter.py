import unittest

from routeconv.converter import RouteSyntaxError, express_to_flask, flask_to_express


class FlaskToExpressTests(unittest.TestCase):
    def test_no_parameters(self):
        self.assertEqual(flask_to_express("/health"), "/health")

    def test_default_converter_is_string(self):
        self.assertEqual(flask_to_express("/users/<name>"), "/users/:name")

    def test_explicit_string_converter_has_no_constraint(self):
        self.assertEqual(flask_to_express("/users/<string:name>"), "/users/:name")

    def test_int_converter(self):
        self.assertEqual(flask_to_express("/users/<int:id>"), r"/users/:id(\d+)")

    def test_float_converter(self):
        self.assertEqual(
            flask_to_express("/prices/<float:amount>"), r"/prices/:amount(\d+\.\d+)"
        )

    def test_uuid_converter(self):
        self.assertEqual(
            flask_to_express("/items/<uuid:id>"),
            r"/items/:id([0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-"
            r"[0-9a-fA-F]{4}-[0-9a-fA-F]{12})",
        )

    def test_path_converter(self):
        self.assertEqual(flask_to_express("/files/<path:filepath>"), "/files/:filepath(.*)")

    def test_multiple_parameters(self):
        self.assertEqual(
            flask_to_express("/users/<int:id>/posts/<slug>"),
            r"/users/:id(\d+)/posts/:slug",
        )

    def test_unexpected_closing_bracket(self):
        with self.assertRaises(RouteSyntaxError) as ctx:
            flask_to_express("/a>b")
        self.assertEqual(ctx.exception.column, 3)

    def test_unterminated_parameter(self):
        with self.assertRaises(RouteSyntaxError) as ctx:
            flask_to_express("/users/<int:id/comments")
        self.assertEqual(ctx.exception.column, 8)
        self.assertIsNotNone(ctx.exception.hint)

    def test_too_many_colons(self):
        with self.assertRaises(RouteSyntaxError) as ctx:
            flask_to_express("/x/<int:id:extra>")
        self.assertEqual(ctx.exception.column, 11)

    def test_empty_converter(self):
        with self.assertRaises(RouteSyntaxError) as ctx:
            flask_to_express("/x/<:id>")
        self.assertEqual(ctx.exception.column, 5)

    def test_unknown_converter(self):
        with self.assertRaises(RouteSyntaxError) as ctx:
            flask_to_express("/x/<foo:id>")
        self.assertEqual(ctx.exception.column, 5)
        self.assertIn("string", ctx.exception.hint)

    def test_empty_name(self):
        with self.assertRaises(RouteSyntaxError) as ctx:
            flask_to_express("/x/<int:>")
        self.assertEqual(ctx.exception.column, 9)

    def test_empty_name_default_converter(self):
        with self.assertRaises(RouteSyntaxError) as ctx:
            flask_to_express("/x/<>")
        self.assertEqual(ctx.exception.column, 5)

    def test_invalid_character_in_name(self):
        with self.assertRaises(RouteSyntaxError) as ctx:
            flask_to_express("/x/<int:i-d>")
        self.assertEqual(ctx.exception.column, 10)

    def test_line_number_is_carried_through(self):
        with self.assertRaises(RouteSyntaxError) as ctx:
            flask_to_express("/x/<foo:id>", line=7)
        self.assertEqual(ctx.exception.line, 7)


class ExpressToFlaskTests(unittest.TestCase):
    def test_no_parameters(self):
        self.assertEqual(express_to_flask("/health"), "/health")

    def test_parameter_without_constraint(self):
        self.assertEqual(express_to_flask("/users/:name"), "/users/<name>")

    def test_int_constraint(self):
        self.assertEqual(express_to_flask(r"/users/:id(\d+)"), "/users/<int:id>")

    def test_float_constraint(self):
        self.assertEqual(
            express_to_flask(r"/prices/:amount(\d+\.\d+)"), "/prices/<float:amount>"
        )

    def test_uuid_constraint(self):
        self.assertEqual(
            express_to_flask(
                r"/items/:id([0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-"
                r"[0-9a-fA-F]{4}-[0-9a-fA-F]{12})"
            ),
            "/items/<uuid:id>",
        )

    def test_path_constraint(self):
        self.assertEqual(express_to_flask("/files/:filepath(.*)"), "/files/<path:filepath>")

    def test_multiple_parameters(self):
        self.assertEqual(
            express_to_flask(r"/users/:id(\d+)/posts/:slug"),
            "/users/<int:id>/posts/<slug>",
        )

    def test_name_stops_at_non_name_character(self):
        self.assertEqual(express_to_flask(":na-me"), "<na>-me")

    def test_wildcard_is_rejected(self):
        with self.assertRaises(RouteSyntaxError) as ctx:
            express_to_flask("/files/*")
        self.assertEqual(ctx.exception.column, 8)
        self.assertIsNotNone(ctx.exception.hint)

    def test_missing_name_after_colon(self):
        with self.assertRaises(RouteSyntaxError) as ctx:
            express_to_flask("/users/:")
        self.assertEqual(ctx.exception.column, 8)

    def test_unterminated_constraint(self):
        with self.assertRaises(RouteSyntaxError) as ctx:
            express_to_flask("/x/:id(abc")
        self.assertEqual(ctx.exception.column, 7)

    def test_unmapped_constraint(self):
        with self.assertRaises(RouteSyntaxError) as ctx:
            express_to_flask("/x/:id(abc)")
        self.assertEqual(ctx.exception.column, 8)
        self.assertIsNotNone(ctx.exception.hint)

    def test_optional_parameter_without_constraint_is_rejected(self):
        with self.assertRaises(RouteSyntaxError) as ctx:
            express_to_flask("/x/:id?")
        self.assertEqual(ctx.exception.column, 7)

    def test_optional_parameter_with_constraint_is_rejected(self):
        with self.assertRaises(RouteSyntaxError) as ctx:
            express_to_flask(r"/x/:id(\d+)?")
        self.assertEqual(ctx.exception.column, 12)
        self.assertIn("split", ctx.exception.hint)


class RoundTripTests(unittest.TestCase):
    PATTERNS = [
        "/health",
        "/users/<name>",
        "/users/<int:id>",
        "/prices/<float:amount>",
        "/files/<path:filepath>",
        "/users/<int:id>/posts/<slug>",
    ]

    def test_flask_express_flask(self):
        for pattern in self.PATTERNS:
            with self.subTest(pattern=pattern):
                express = flask_to_express(pattern)
                self.assertEqual(express_to_flask(express), pattern)


class RouteSyntaxErrorTests(unittest.TestCase):
    def test_str_includes_pointer_and_hint(self):
        exc = RouteSyntaxError("bad thing", column=3, source="/a/b", line=2, hint="fix it")
        rendered = str(exc)
        lines = rendered.splitlines()
        self.assertEqual(lines[0], "line 2, column 3: bad thing")
        self.assertEqual(lines[1], "    /a/b")
        self.assertEqual(lines[2], "    " + " " * 2 + "^")
        self.assertEqual(lines[3], "    hint: fix it")

    def test_str_without_hint_omits_hint_line(self):
        exc = RouteSyntaxError("bad thing", column=1, source="/a", line=1)
        self.assertNotIn("hint", str(exc))


if __name__ == "__main__":
    unittest.main()
