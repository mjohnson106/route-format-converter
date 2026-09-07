import contextlib
import io
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from routeconv.cli import convert_stream, main


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
        results, errors = convert_stream(handle, "express")
        self.assertEqual(results, [r"/users/:id(\d+)", "/health"])
        self.assertEqual(errors, [])

    def test_bad_line_does_not_stop_the_rest(self):
        handle = io.StringIO("/x/<foo:id>\n/users/<int:id>\n")
        results, errors = convert_stream(handle, "express")
        self.assertEqual(results, [r"/users/:id(\d+)"])
        self.assertEqual(len(errors), 1)
        self.assertEqual(errors[0].line, 1)

    def test_to_flask(self):
        handle = io.StringIO(r"/users/:id(\d+)" + "\n")
        results, errors = convert_stream(handle, "flask")
        self.assertEqual(results, ["/users/<int:id>"])
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


if __name__ == "__main__":
    unittest.main()
