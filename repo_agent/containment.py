"""Execution containment (C-A): levels, podman execution, and probes.

Levels, stated honestly:
- "container": verify-phase commands run under rootless podman with no
  network, a read-only root filesystem, and only the verification
  environment mounted (SELinux :Z labeled). This is about the strongest
  verification environment, not a claim about the worker phase.
- "isolation_by_construction": disposable workspace, env allowlist,
  argv-only subprocess. A fresh directory is not a sandbox.

Podman runs with the caller's environment; only -e flags configure the
container (rewriting HOME/PATH for the podman process detaches it from
its rootless storage). Verification never auto-pulls: the image is an
operator-provisioned pin.
"""
import os
import shutil
import signal
import subprocess
from pathlib import Path

PROBE_IMAGE = "docker.io/library/python:3.12-slim"
_CONTAINER_WORK = "/work"


def _run_argv(
    argv: list[str], cwd: Path, env: dict[str, str], timeout: int
) -> tuple[int, str]:
    proc = subprocess.Popen(
        argv,
        cwd=cwd,
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        start_new_session=True,
    )
    assert proc.stdout is not None
    try:
        out = proc.stdout.read(200_000).decode("utf-8", errors="replace")
        code = proc.wait(timeout=timeout)
    except subprocess.TimeoutExpired:
        try:
            os.killpg(proc.pid, signal.SIGKILL)
        except (ProcessLookupError, PermissionError):
            proc.kill()
        code = proc.wait()
        out += "\n[timeout: process group killed]"
    return code, out


def _podman() -> str | None:
    return shutil.which("podman")

def _image_ready() -> bool:
    podman = _podman()
    if podman is None:
        return False
    return (
        subprocess.run(
            [podman, "image", "exists", PROBE_IMAGE], capture_output=True
        ).returncode
        == 0
    )

def containment_level() -> str:
    """The strongest execution containment available on this host.

    "container" means verify-phase commands run under rootless podman with
    no network and a read-only root filesystem. It is about the strongest
    verification environment, not a claim about the worker phase, which
    stays at isolation_by_construction.
    """
    return "container" if _image_ready() else "isolation_by_construction"


_CONTAINER_WORK = "/work"


def _execute(
    argv: list[str],
    env_dir: Path,
    env: dict[str, str],
    timeout: int,
    level: str,
) -> tuple[int, str]:
    """Run one command at the given containment level.

    Container level: rootless podman, no network, read-only root
    filesystem, the verification environment mounted at /work. Host paths
    in argv and env that point into the environment are rewritten to
    their container paths.
    """
    if level != "container" or _podman() is None:
        return _run_argv(argv, cwd=env_dir, env=env, timeout=timeout)

    def rewrite(value: str) -> str:
        prefix = str(env_dir)
        if value == prefix:
            return _CONTAINER_WORK
        if value.startswith(prefix + "/"):
            return _CONTAINER_WORK + value[len(prefix):]
        return value

    container_env: list[str] = []
    for key, value in env.items():
        container_env += ["-e", f"{key}={rewrite(value)}"]
    podman_argv = [
        _podman() or "podman",
        "run",
        "--rm",
        "--network=none",
        "--read-only",
        "--userns=keep-id",
        "-v", f"{env_dir.resolve()}:{_CONTAINER_WORK}:Z",
        "-w", _CONTAINER_WORK,
        "--pull=never",
        *container_env,
        PROBE_IMAGE,
        *[rewrite(arg) for arg in argv],
    ]
    # podman itself runs with the caller's environment: rewriting HOME or
    # PATH for the podman process detaches it from its rootless storage;
    # only the -e flags configure the container.
    return _run_argv(podman_argv, cwd=env_dir, env=dict(os.environ), timeout=timeout)

def _probe(image_ready: bool, argv: list[str]) -> str:
    if not image_ready:
        return "unavailable"
    proc = subprocess.run(
        argv, capture_output=True, text=True, timeout=90, start_new_session=True
    )
    return "denied" if proc.returncode != 0 else "LEAKED"

def run_containment_probes(work_root: Path) -> dict[str, object]:
    """podman-backed probes; a missing podman or image is a named skip."""
    work_root = Path(work_root)
    work_root.mkdir(parents=True, exist_ok=True)
    podman = shutil.which("podman")
    if podman is None:
        return {
            "podman": "absent",
            "level": "isolation_by_construction",
            "egress_deny": "unavailable",
            "readonly_mount": "unavailable",
            "note": "install rootless podman to enable container-level probes",
        }
    image_ready = (
        subprocess.run(
            [podman, "image", "exists", PROBE_IMAGE], capture_output=True
        ).returncode
        == 0
    )
    scratch = work_root / "readonly-probe"
    scratch.mkdir(exist_ok=True)
    (scratch / "keep.txt").write_text("probe\n", encoding="utf-8")
    egress = _probe(
        image_ready,
        [podman, "run", "--rm", "--network=none", PROBE_IMAGE,
         "bash", "-c", "echo > /dev/tcp/example.com/80"],
    )
    readonly = _probe(
        image_ready,
        [podman, "run", "--rm", "--network=none",
         # :Z relabels for SELinux; with that in place a nonzero exit
         # from touch can only be the read-only mount.
         "-v", f"{scratch.resolve()}:/mnt:ro,Z", PROBE_IMAGE,
         "touch", "/mnt/attempted-write"],
    )
    return {
        "podman": "present",
        "level": "container",
        "image": PROBE_IMAGE if image_ready else "not pulled",
        "egress_deny": egress,
        "readonly_mount": readonly,
    }


