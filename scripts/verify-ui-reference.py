"""Compare actual product-content captures with the accepted, read-only design."""
import argparse
import hashlib
import json
import math
from pathlib import Path
from PIL import Image, ImageChops


def compare(reference: Path, actual: Path, threshold: float = .12) -> dict:
    with Image.open(reference) as image:
        expected = image.convert("RGB")
    if expected.size == (1280, 820):
        expected = expected.crop((0, 38, 1280, 820))
    with Image.open(actual) as image:
        observed = image.convert("RGB")
    if expected.size != observed.size:
        return {"passed": False, "error": "dimensions", "expected": expected.size, "actual": observed.size}
    difference = ImageChops.difference(expected, observed)
    pixels = difference.get_flattened_data() if hasattr(difference, "get_flattened_data") else difference.getdata()
    changed = sum(max(pixel) / 255 > threshold for pixel in pixels)
    ratio = changed / (observed.width * observed.height)
    return {"passed": ratio <= .01, "different_pixels": changed, "difference_ratio": ratio,
            "threshold": threshold, "maximum_difference_ratio": .01, "size": observed.size}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--reference", type=Path, required=True)
    parser.add_argument("--actual", type=Path, required=True)
    parser.add_argument("--native", type=Path, help="Require fresh actual native pet captures too")
    args = parser.parse_args()
    project = args.reference.resolve().parents[2]
    manifest = json.loads((args.reference / "reference-manifest.json").read_text())
    if manifest["status"] != "accepted" or manifest.get("knownIssues"):
        raise SystemExit("Design reference is not accepted or has unresolved issues")
    for entry in manifest["files"]:
        if hashlib.sha256((project / entry["path"]).read_bytes()).hexdigest() != entry["sha256"]:
            raise SystemExit("Reference changed without acceptance: " + entry["path"])
    result = {}
    for page in ("today", "calendar", "tasks", "assistant", "settings", "task-detail", "import-default"):
        name = page + (".png" if page in ("task-detail", "import-default") else "-desktop.png")
        actual = args.actual / name
        result[page] = compare(args.reference / "screens" / name, actual) if actual.exists() else {"passed": False, "error": "missing actual capture"}
    geometry_path = args.actual / "geometry.json"
    if geometry_path.exists():
        geometry = json.loads(geometry_path.read_text())
        result["geometry"] = {"passed": isinstance(geometry,dict) and set(geometry)=={"today","calendar","tasks","assistant","settings"} and all(isinstance(g,dict) and all(isinstance(g.get(k),(int,float)) and math.isfinite(g[k]) and abs(g[k]-v)<=2 for k,v in {"x":214,"y":31,"width":1028,"height":43}.items()) for g in geometry.values()), "actual": geometry}
    else:
        result["geometry"]={"passed":False,"error":"missing geometry evidence"}
    if args.native:
        for name in ("pet-idle","pet-todos","pet-detail"):
            actual=args.native/(name+".png")
            result[name]=compare(args.reference/"screens"/(name+".png"),actual) if actual.exists() else {"passed":False,"error":"missing native capture"}
    passed = all(r["passed"] for r in result.values())
    report = {"passed": passed, "kind": "same-fixture-design-comparison", "results": result}
    (args.actual / "comparison.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps(report, ensure_ascii=False))
    raise SystemExit(0 if passed else 1)


if __name__ == "__main__":
    main()
