"""Build a code-only Lambda ZIP with Linux wheels already staged by uv."""
from pathlib import Path
import zipfile

ROOT=Path(__file__).resolve().parents[1]


def main():
    runtime=ROOT/"artifacts/lambda-runtime"
    if not (runtime/"mangum").is_dir():
        raise RuntimeError("Stage Linux dependencies from deploy/requirements.lambda.txt first")
    output=ROOT/"artifacts/Baton_lambda.zip"
    with zipfile.ZipFile(output,"w",zipfile.ZIP_DEFLATED) as archive:
        for folder,base in [(runtime,runtime)]+[(ROOT/name,ROOT) for name in ("baton","server","web","fixtures","third_party")]:
            for path in folder.rglob("*"):
                if path.is_file() and "__pycache__" not in path.parts and not path.name.startswith(".env"):
                    archive.write(path,path.relative_to(base).as_posix())
        for path in (ROOT / "docs/evidence").rglob("*"):
            if path.is_file() and not path.name.startswith("."):
                archive.write(path, "web/evidence/" + path.relative_to(ROOT / "docs/evidence").as_posix())
    if output.stat().st_size>49*1024*1024:
        raise RuntimeError("Deployment exceeds the direct Lambda upload bound")
    print(f"{output} ({output.stat().st_size:,} bytes)")


if __name__=="__main__":
    main()
