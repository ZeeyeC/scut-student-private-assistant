"""Source checkout convenience entry; packaged end users use the .app/.exe."""

import sys
from pathlib import Path

root = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(root / "backend"))
from app.launcher import main

sys.argv[1:1] = ["--data-dir", str(root), "--project"]
raise SystemExit(main())
