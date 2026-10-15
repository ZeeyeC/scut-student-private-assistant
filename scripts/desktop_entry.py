"""PyInstaller entry point, no user configuration embedded here."""

from app.launcher import main

if __name__ == "__main__":
    raise SystemExit(main())
