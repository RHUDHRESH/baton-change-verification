"""Stage public static assets and an exact Lambda API proxy; never upload secrets."""
import argparse
import json
from pathlib import Path
import shutil
import tarfile
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parents[1]


def stage(backend):
    parsed = urlparse(backend)
    if parsed.scheme != "https" or not parsed.hostname.endswith(".lambda-url.ap-south-1.on.aws"):
        raise ValueError("Expected the app's Mumbai Lambda HTTPS Function URL")
    target = ROOT / "artifacts/vercel-frontend"
    target.mkdir(parents=True, exist_ok=True)
    shutil.copytree(ROOT / "web", target, dirs_exist_ok=True)
    from server.security import POLICY
    config = {"$schema": "https://openapi.vercel.sh/vercel.json", "cleanUrls": False,
              "rewrites": [{"source": "/api/:path*", "destination": backend.rstrip("/") + "/api/:path*"}],
              "headers": [{"source": "/(.*)", "headers": [
                  {"key": "Content-Security-Policy", "value": POLICY},
                  {"key": "X-Content-Type-Options", "value": "nosniff"},
                  {"key": "X-Frame-Options", "value": "DENY"},
                  {"key": "Referrer-Policy", "value": "same-origin"}]}]}
    (target / "vercel.json").write_text(json.dumps(config, indent=2), encoding="utf-8")
    archive = ROOT / "artifacts/vercel-frontend.tgz"
    with tarfile.open(archive, "w:gz") as out:
        for path in sorted(target.rglob("*")):
            if path.is_file() and ".vercel" not in path.parts:
                out.add(path, arcname=path.relative_to(target).as_posix())
    print(archive)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("backend")
    stage(parser.parse_args().backend)
