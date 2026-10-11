import gzip, hashlib, json, os, shutil, sys
from pathlib import Path

tag, repo = sys.argv[1], os.environ["GITHUB_REPOSITORY"]
cfg = json.loads(Path("datasets.json").read_text())
dist = Path("dist")
manifest = {"min_app_version": cfg["min_app_version"], "datasets": {}}

for name, meta in cfg["datasets"].items():
    gz = dist / f"{name}.db.gz"
    with open(dist / f"{name}.db", "rb") as src, open(gz, "wb") as raw, \
         gzip.GzipFile(fileobj=raw, mode="wb", compresslevel=9, mtime=0) as out:
        shutil.copyfileobj(src, out)
    manifest["datasets"][name] = {
        **meta,
        "url": f"https://github.com/{repo}/releases/download/{tag}/{gz.name}",
        "sha256": hashlib.sha256(gz.read_bytes()).hexdigest(),
        "size": gz.stat().st_size,
    }

(dist / "manifest.json").write_text(json.dumps(manifest, indent=2))