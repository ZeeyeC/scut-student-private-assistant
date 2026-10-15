import hashlib
import json
import sqlite3
import tempfile
import zipfile
from pathlib import Path


def backup(database, checkpoint, uploads, output):
    database, checkpoint, uploads, output = map(
        Path, (database, checkpoint, uploads, output)
    )
    if Path(str(database) + ".server.lock").exists():
        raise ValueError("请先停止助手服务，再做一致备份")
    if output.exists():
        raise ValueError("不覆盖已有备份")
    with tempfile.TemporaryDirectory() as temp:
        root = Path(temp)
        files = {}
        for source, name in [(database, "campus.db"), (checkpoint, "agent.db")]:
            if not source.is_file():
                raise ValueError("数据库不存在：" + str(source))
            with (
                sqlite3.connect(f"file:{source}?mode=ro", uri=True) as src,
                sqlite3.connect(root / name) as dst,
            ):
                src.backup(dst)
            with sqlite3.connect(root / name) as db:
                if db.execute("pragma integrity_check").fetchone()[0] != "ok":
                    raise ValueError("数据库完整性检查失败")
            files[name] = (root / name).read_bytes()
        for file in uploads.glob("*.png"):
            if file.is_symlink():
                raise ValueError("图片目录不允许符号链接")
            files["uploads/" + file.name] = file.read_bytes()
        manifest = {
            name: hashlib.sha256(data).hexdigest() for name, data in files.items()
        }
        output.parent.mkdir(parents=True, exist_ok=True)
        with zipfile.ZipFile(output, "x", compression=zipfile.ZIP_DEFLATED) as z:
            z.writestr("manifest.json", json.dumps(manifest))
            for name, data in files.items():
                z.writestr(name, data)


def restore(package, target):
    target = Path(target)
    if target.exists() and any(target.iterdir()):
        raise ValueError("只恢复到空目录，不覆盖现有数据")
    with zipfile.ZipFile(package) as z:
        manifest = json.loads(z.read("manifest.json"))
        if not {"campus.db", "agent.db"} <= set(manifest):
            raise ValueError("备份缺少数据库")
        files = {}
        for name, expected in manifest.items():
            p = Path(name)
            if (
                p.is_absolute()
                or ".." in p.parts
                or (
                    name not in ("campus.db", "agent.db")
                    and not (p.parent == Path("uploads") and p.suffix == ".png")
                )
            ):
                raise ValueError("备份路径无效")
            data = z.read(name)
            if hashlib.sha256(data).hexdigest() != expected:
                raise ValueError("备份校验失败")
            files[name] = data
        target.mkdir(parents=True, exist_ok=True)
        for name, data in files.items():
            dest = target / name
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_bytes(data)
