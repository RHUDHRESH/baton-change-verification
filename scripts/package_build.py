"""Create a local handoff containing source, Git history, tests and demo evidence."""
from pathlib import Path
import subprocess
from zipfile import ZipFile, ZIP_DEFLATED

ROOT = Path(__file__).resolve().parents[1]
ARTIFACTS = ROOT / "artifacts"


def git(*args):
    return subprocess.run(["git", *map(str, args)], cwd=ROOT, check=True, capture_output=True, text=True)


def main():
    if git("status", "--porcelain").stdout.strip():
        raise SystemExit("Commit the reviewed source before creating the handoff.")
    ARTIFACTS.mkdir(exist_ok=True)
    source = ARTIFACTS / "Baton_source.zip"
    bundle = ARTIFACTS / "baton.bundle"
    git("archive", "--format=zip", f"--output={source}", "HEAD")
    git("bundle", "create", bundle, "--all")
    files = [source, bundle, *ARTIFACTS.glob("dist/*.whl"), *ARTIFACTS.glob("*tests.xml"), ARTIFACTS / "check-run.json",
             ROOT / "loop/last_score.json", ROOT / "loop/junit.xml", ROOT / "docs/BUILD_REPORT.md",
             ROOT / "output/playwright/baton-demo.webm", ROOT / "output/playwright/desktop.png",
             ROOT / "output/playwright/mobile.png", ROOT / "output/playwright/mobile-dark.png"]
    output = ARTIFACTS / "Baton_complete_build.zip"
    with ZipFile(output, "w", ZIP_DEFLATED) as archive:
        for path in files:
            if path.is_file():
                archive.write(path, path.relative_to(ROOT).as_posix())
        archive.writestr("START_HERE.txt", "Baton local build\n\nFor complete Git history (required by one ZIP test):\n  git clone artifacts/baton.bundle Baton\n  cd Baton\n  docker compose up -d --build\n\nOpen http://127.0.0.1:8000\nRun checks: docker compose --profile checks run --build --rm checks\n\nBaton_source.zip also contains the source without history.\nPublic hosting, fresh paid-model runs and event submission are not included.\n")
    print(output)


if __name__ == "__main__":
    main()
