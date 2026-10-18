import json, os, shutil, socket, subprocess, sys, time
from pathlib import Path
import pytest

ROOT = Path(__file__).resolve().parents[3]
HERE = Path(__file__).resolve().parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))
S = "/tmp/claude-0/-home-claude/9e986261-4c5d-5119-82fd-cce4a3dc1af5/scratchpad"
REDIS = os.environ.get("BATON_TEST_REDIS", S + "/venv/lib/python3.13/site-packages/redislite/bin/redis-server")
MODULE = os.environ.get("BATON_TEST_MODULE", S + "/fdb422/falkordb.so")


def _free_port():
    s = socket.socket(); s.bind(("127.0.0.1", 0)); p = s.getsockname()[1]; s.close(); return p


@pytest.fixture(scope="session")
def port(tmp_path_factory):
    p = _free_port()
    d = tmp_path_factory.mktemp("falkor")
    proc = subprocess.Popen([REDIS, "--port", str(p), "--dir", str(d), "--loadmodule", MODULE, "--save", "",
                             "--logfile", str(d / "r.log")])
    for _ in range(100):
        try:
            socket.create_connection(("127.0.0.1", p), timeout=0.2).close(); break
        except OSError:
            time.sleep(0.1)
    yield p
    proc.terminate(); proc.wait(timeout=10)


def baton(*args, check=True):
    r = subprocess.run([sys.executable, "-m", "baton", *map(str, args)], cwd=ROOT, capture_output=True, text=True,
                       timeout=180)
    if check and r.returncode != 0:
        raise AssertionError(f"baton {args} exited {r.returncode}\nSTDOUT:{r.stdout[-2000:]}\nSTDERR:{r.stderr[-2000:]}")
    return r


def baton_json(*args):
    return json.loads(baton(*args).stdout)


@pytest.fixture(scope="session")
def worlds(tmp_path_factory):
    cache = {}

    def get(seed):
        if seed not in cache:
            d = tmp_path_factory.mktemp(f"w{seed}")
            baton("generate", "--seed", seed, "--out", d)
            cache[seed] = (d, json.loads((d / "world.json").read_text()), json.loads((d / "answer_key.json").read_text()))
        return cache[seed]
    return get


def write_beliefs(d, beliefs, name="beliefs.json"):
    p = Path(d) / name
    p.write_text(json.dumps(beliefs))
    return p
