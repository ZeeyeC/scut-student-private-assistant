# Build natively on each target OS/architecture. Never collect .env or user data.
import sys
from pathlib import Path
from PyInstaller.utils.hooks import collect_data_files, collect_submodules, copy_metadata

root = Path(SPECPATH).parent
metadata = []
for name in ("deepagents", "langchain", "langchain-core", "langchain-openai", "langgraph", "langgraph-prebuilt", "langgraph-checkpoint", "langgraph-checkpoint-sqlite", "langgraph-sdk", "fastapi-users", "mcp-server-time", "langchain-mcp-adapters", "mcp", "markitdown", "mcp-server-fetch", "qdrant-client", "fastembed", "onnxruntime", "tokenizers", "magika"):
    metadata += copy_metadata(name, recursive=True)
data = [(str(root / "frontend" / "dist"), "frontend/dist"), (str(root / "backend" / "alembic.ini"), "backend"), (str(root / "backend" / "migrations"), "backend/migrations"), (str(root / "config" / "scut-undergraduate-2026-10-14.json"), "config"), (str(root / "extension" / ".output" / "chrome-mv3"), "extension/.output/chrome-mv3")]
for package in ("deepagents", "langchain", "langchain_core", "langgraph", "tzdata", "markitdown", "magika", "pptx", "openpyxl", "fastembed", "onnxruntime", "tokenizers"):
    data += collect_data_files(package, include_py_files=False)
hidden = collect_submodules("markitdown") + collect_submodules("qdrant_client") + collect_submodules("fastembed") + collect_submodules("mcp_server_fetch") + collect_submodules("app") + collect_submodules("langgraph.checkpoint.sqlite") + collect_submodules("uvicorn.loops") + collect_submodules("uvicorn.protocols") + collect_submodules("uvicorn.lifespan")
a = Analysis([str(root / "scripts" / "desktop_entry.py")], pathex=[str(root / "backend")], binaries=[], datas=data + metadata, hiddenimports=hidden, hookspath=[], hooksconfig={}, runtime_hooks=[], excludes=["pytest", "IPython", "notebook", "matplotlib", "tkinter"], noarchive=False)
pyz = PYZ(a.pure)
exe = EXE(pyz, a.scripts, [], exclude_binaries=True, name="CampusCompanion", debug=False, bootloader_ignore_signals=False, strip=False, upx=False, console=False, disable_windowed_traceback=False)
coll = COLLECT(exe, a.binaries, a.datas, strip=False, upx=False, name="CampusCompanion")
if sys.platform == "darwin":
    app = BUNDLE(coll, name="课间助手.app", bundle_identifier="cn.campuscompanion.local", version="0.1.0", info_plist={"CFBundleDisplayName": "课间助手", "NSHighResolutionCapable": True})
