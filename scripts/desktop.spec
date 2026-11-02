# Build natively on each target OS/architecture. Never collect .env or user data.
import sys
import json
import runpy
from pathlib import Path
from PyInstaller.utils.hooks import collect_data_files, collect_submodules, copy_metadata

root = Path(SPECPATH).parent
runtime = runpy.run_path(str(root / "backend/app/desktop_handoff.py"))["runtime_manifest"](root)
runtime_file = root / "campus-pet/build/service-build.json"
runtime_file.parent.mkdir(parents=True, exist_ok=True)
runtime_file.write_text(json.dumps(runtime), encoding="utf-8")
metadata = []
for name in ("deepagents", "langchain", "langchain-core", "langchain-openai", "langgraph", "langgraph-prebuilt", "langgraph-checkpoint", "langgraph-checkpoint-sqlite", "langgraph-sdk", "fastapi-users", "mcp-server-time", "langchain-mcp-adapters", "mcp", "markitdown", "mcp-server-fetch", "qdrant-client", "fastembed", "onnxruntime", "tokenizers", "magika", "zotero-mcp-server", "fastmcp", "fastmcp-slim", "pyzotero", "pdf-inspector"):
    metadata += copy_metadata(name, recursive=True)
data = [(str(root / "frontend" / "dist"), "frontend/dist"), (str(root / "backend" / "alembic.ini"), "backend"), (str(root / "backend" / "migrations"), "backend/migrations"), (str(root / "config" / "scut-undergraduate-2026-10-14.json"), "config"), (str(root / "extension" / ".output" / "chrome-mv3"), "extension/.output/chrome-mv3")]
data.append((str(runtime_file), "."))
for package in ("deepagents", "langchain", "langchain_core", "langgraph", "tzdata", "markitdown", "magika", "pptx", "openpyxl", "fastembed", "onnxruntime", "tokenizers", "zotero_mcp", "fastmcp", "pyzotero"):
    data += collect_data_files(package, include_py_files=False)
hidden = collect_submodules("pdf_inspector") + collect_submodules("zotero_mcp") + collect_submodules("fastmcp") + collect_submodules("pyzotero") + collect_submodules("markitdown") + collect_submodules("qdrant_client") + collect_submodules("fastembed") + collect_submodules("mcp_server_fetch") + collect_submodules("app") + collect_submodules("langgraph.checkpoint.sqlite") + collect_submodules("uvicorn.loops") + collect_submodules("uvicorn.protocols") + collect_submodules("uvicorn.lifespan")
a = Analysis([str(root / "scripts" / "desktop_entry.py")], pathex=[str(root / "backend")], binaries=[], datas=data + metadata, hiddenimports=hidden, hookspath=[], hooksconfig={}, runtime_hooks=[], excludes=["pytest", "IPython", "notebook", "matplotlib", "tkinter"], noarchive=False)
pyz = PYZ(a.pure)
exe = EXE(pyz, a.scripts, [], exclude_binaries=True, name="CampusCompanion", debug=False, bootloader_ignore_signals=False, strip=False, upx=False, console=False, disable_windowed_traceback=False)
coll = COLLECT(exe, a.binaries, a.datas, strip=False, upx=False, name="CampusCompanion")
if sys.platform == "darwin":
    app = BUNDLE(coll, name="课间助手.app", bundle_identifier="cn.campuscompanion.local", version="0.1.0", info_plist={"CFBundleDisplayName": "课间助手", "NSHighResolutionCapable": True})
