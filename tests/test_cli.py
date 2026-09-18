import contextlib
import io
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from routeconv.cli import convert_stream, main
from routeconv.converter import (
    django_to_express,
    express_to_django,
    express_to_flask,
    express_to_flask_rules,
    flask_to_django,
    flask_to_express,
)


class ConvertStreamTests(unittest.TestCase):
    def test_skips_blank_and_comment_lines(self):
        handle = io.StringIO(
            "\n"
            "# a comment\n"
            "/users/<int:id>\n"
            "   \n"
            "   # indented comment\n"
            "/health\n"
        )
        results, errors = convert_stream(handle, flask_to_express)
        self.assertEqual(results, [r"/users/:id(\d+)", "/health"])
        self.assertEqual(errors, [])

    def test_bad_line_does_not_stop_the_rest(self):
        handle = io.StringIO("/x/<foo:id>\n/users/<int:id>\n")
        results, errors = convert_stream(handle, flask_to_express)
        self.assertEqual(results, [r"/users/:id(\d+)"])
        self.assertEqual(len(errors), 1)
        self.assertEqual(errors[0].line, 1)

    def test_to_flask(self):
        handle = io.StringIO(r"/users/:id(\d+)" + "\n")
        results, errors = convert_stream(handle, express_to_flask)
        self.assertEqual(results, ["/users/<int:id>"])
        self.assertEqual(errors, [])

    def test_to_django(self):
        handle = io.StringIO(r"/users/:pk([0-9]+)" + "\n")
        results, errors = convert_stream(handle, express_to_django)
        self.assertEqual(results, ["/users/<int:pk>"])
        self.assertEqual(errors, [])

    def test_from_django(self):
        handle = io.StringIO("/users/<int:pk>\n")
        results, errors = convert_stream(handle, django_to_express)
        self.assertEqual(results, [r"/users/:pk([0-9]+)"])
        self.assertEqual(errors, [])

    def test_flask_to_django_direct(self):
        handle = io.StringIO("/users/<int:id>\n")
        results, errors = convert_stream(handle, flask_to_django)
        self.assertEqual(results, ["/users/<int:id>"])
        self.assertEqual(errors, [])

    def test_list_results_are_flattened(self):
        handle = io.StringIO("/users/:id?\n/health\n")
        results, errors = convert_stream(handle, express_to_flask_rules)
        self.assertEqual(results, ["/users/<id>", "/users", "/health"])
        self.assertEqual(errors, [])


class MainTests(unittest.TestCase):
    def _run(self, argv, stdin_text=""):
        out, err = io.StringIO(), io.StringIO()
        with mock.patch("sys.stdin", io.StringIO(stdin_text)):
            with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
                status = main(argv)
        return status, out.getvalue(), err.getvalue()

    def test_reads_stdin_by_default(self):
        status, out, err = self._run(["--to", "express"], "/users/<int:id>\n")
        self.assertEqual(status, 0)
        self.assertEqual(out, r"/users/:id(\d+)" + "\n")
        self.assertEqual(err, "")

    def test_errors_go_to_stderr_with_nonzero_exit(self):
        status, out, err = self._run(["--to", "express"], "/x/<foo:id>\n")
        self.assertEqual(status, 1)
        self.assertEqual(out, "")
        self.assertIn("<stdin>:", err)

    def test_reads_from_file_path(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "routes.txt"
            path.write_text("/users/<int:id>\n/x/<foo:id>\n", encoding="utf-8")
            status, out, err = self._run(["--to", "express", str(path)])
        self.assertEqual(status, 1)
        self.assertEqual(out, r"/users/:id(\d+)" + "\n")
        self.assertIn(f"{path}:", err)

    def test_explicit_from_to_django(self):
        status, out, err = self._run(
            ["--to", "django", "--from", "express"], r"/users/:pk([0-9]+)" + "\n"
        )
        self.assertEqual(status, 0)
        self.assertEqual(out, "/users/<int:pk>\n")
        self.assertEqual(err, "")

    def test_explicit_from_django_to_express(self):
        status, out, err = self._run(
            ["--to", "express", "--from", "django"], "/users/<int:pk>\n"
        )
        self.assertEqual(status, 0)
        self.assertEqual(out, r"/users/:pk([0-9]+)" + "\n")
        self.assertEqual(err, "")

    def test_django_without_explicit_from_is_rejected(self):
        with self.assertRaises(SystemExit):
            self._run(["--to", "django"], "/health\n")

    def test_explicit_from_flask_to_django(self):
        status, out, err = self._run(
            ["--to", "django", "--from", "flask"], "/users/<uuid:id>\n"
        )
        self.assertEqual(status, 0)
        self.assertEqual(out, "/users/<uuid:id>\n")
        self.assertEqual(err, "")

    def test_explicit_from_django_to_flask(self):
        status, out, err = self._run(
            ["--to", "flask", "--from", "django"], "/users/<int:pk>\n"
        )
        self.assertEqual(status, 0)
        self.assertEqual(out, "/users/<int:pk>\n")
        self.assertEqual(err, "")

    def test_same_from_and_to_is_rejected(self):
        with self.assertRaises(SystemExit):
            self._run(["--to", "flask", "--from", "flask"], "/health\n")

    def test_express_optional_param_expands_to_multiple_flask_lines(self):
        status, out, err = self._run(["--to", "flask"], "/users/:id?\n")
        self.assertEqual(status, 0)
        self.assertEqual(out, "/users/<id>\n/users\n")
        self.assertEqual(err, "")


if __name__ == "__main__":
    unittest.main()
