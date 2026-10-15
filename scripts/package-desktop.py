"""Run pinned PyInstaller with literal project-directory glob matching."""

import glob
import os
import sys
from contextlib import contextmanager
from pathlib import Path


@contextmanager
def literal_project_globs(root):
    """Preserve wildcard filenames while escaping brackets in the checkout path.

    PyInstaller 6.22.3 uses glob.glob(hook_dir + '/hook-*.py') without
    escaping hook_dir. A checkout named e.g. 'project [test]' otherwise
    silently loses its built-in dependency hooks. Scope the workaround to
    this build process and to the known literal project prefix.
    """
    original = glob.glob
    root = os.fspath(root)

    def project_glob(pathname, *args, **kwargs):
        pattern = os.fspath(pathname)
        prefix = os.fsencode(root) if isinstance(pattern, bytes) else root
        separator = os.fsencode(os.sep) if isinstance(pattern, bytes) else os.sep
        normalized = os.path.normcase(pattern)
        if normalized == os.path.normcase(prefix) or normalized.startswith(
            os.path.normcase(prefix + separator)
        ):
            pattern = glob.escape(prefix) + pattern[len(prefix) :]
        return original(pattern, *args, **kwargs)

    glob.glob = project_glob
    try:
        yield
    finally:
        glob.glob = original


def main():
    # Apply before importing PyInstaller, including modules using `from glob
    # import glob`; do not alter the installed third-party package on disk.
    with literal_project_globs(Path(__file__).resolve().parents[1]):
        from PyInstaller.__main__ import run

        run(sys.argv[1:])


if __name__ == "__main__":
    main()
