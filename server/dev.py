"""Development launcher: runs the API and the client until Ctrl+C.

    uv run dev

Starting each process through `npm run` put batch wrappers (npm.cmd, and
version-manager shims such as mise's) between the terminal and the
server. On Ctrl+C a wrapper could outlive its parent, waiting on a hidden
"Terminate batch job (Y/N)?" prompt and reading every other keystroke
after the shell came back. This launcher owns both processes directly
instead: each runs detached from the terminal's input and in its own
process group, so only the launcher sees Ctrl+C, and it ends each child's
whole process tree before exiting.
"""

import os
import pathlib
import shutil
import signal
import subprocess
import sys
import threading


_ROOT = pathlib.Path(__file__).resolve().parents[1]
_CLIENT_URL = "http://127.0.0.1:18801"
_WAIT_S = 5.0


def _commands() -> dict[str, list[str]]:
  node = shutil.which("node")
  if node is None:
    sys.exit("usched: Node.js is not on PATH; install Node 20+.")
  return {
    "api": [
      sys.executable,
      *("-m", "uvicorn", "server.main:app"),
      *("--host", "127.0.0.1", "--port", "18800", "--reload"),
    ],
    "client": [
      node,
      str(_ROOT / "client" / "node_modules" / "vite" / "bin" / "vite.js"),
      *("client", "--clearScreen", "false"),
    ],
  }


def _start(command: list[str]) -> subprocess.Popen[bytes]:
  """Starts a child that cannot read the terminal or receive its Ctrl+C."""
  if os.name == "nt":
    return subprocess.Popen(
      command,
      cwd=_ROOT,
      stdin=subprocess.DEVNULL,
      creationflags=subprocess.CREATE_NEW_PROCESS_GROUP,
    )
  return subprocess.Popen(
    command, cwd=_ROOT, stdin=subprocess.DEVNULL, start_new_session=True
  )


def _stop(child: subprocess.Popen[bytes]) -> None:
  """Ends a child and every process it started; a no-op once it exited."""
  if child.poll() is not None:
    return
  if os.name == "nt":
    subprocess.run(
      ["taskkill", "/T", "/F", "/PID", str(child.pid)],
      stdout=subprocess.DEVNULL,
      stderr=subprocess.DEVNULL,
      check=False,
    )
    child.wait()
    return
  os.killpg(child.pid, signal.SIGTERM)
  try:
    child.wait(_WAIT_S)
  except subprocess.TimeoutExpired:
    os.killpg(child.pid, signal.SIGKILL)
    child.wait()


def _interrupt(signum: int, frame: object) -> None:
  del signum, frame
  raise KeyboardInterrupt


def _watch(child: subprocess.Popen[bytes], exited: threading.Event) -> None:
  child.wait()
  exited.set()


def main() -> None:
  """Runs both processes until Ctrl+C or until either one exits."""
  commands = _commands()
  # Children run in their own sessions, so a closed terminal (SIGHUP) or a
  # kill (SIGTERM) reaches only the launcher; both must clean up like Ctrl+C.
  for name in ("SIGTERM", "SIGHUP"):
    if (number := getattr(signal, name, None)) is not None:
      signal.signal(number, _interrupt)
  exited = threading.Event()
  children: dict[str, subprocess.Popen[bytes]] = {}
  try:
    for name, command in commands.items():
      children[name] = _start(command)
      threading.Thread(
        target=_watch, args=(children[name], exited), daemon=True
      ).start()
    print(f"usched: open {_CLIENT_URL}; Ctrl+C stops everything.", flush=True)
    # A bounded wait keeps Ctrl+C responsive on Windows, where a blocking
    # wait may not wake for it; one wakeup a second costs nothing.
    while not exited.wait(1.0):
      pass
  except KeyboardInterrupt:
    pass
  finally:
    ended = {
      name: code
      for name, child in children.items()
      if (code := child.poll()) is not None
    }
    for child in children.values():
      _stop(child)
  if ended:
    sys.exit(
      "usched: "
      + ", ".join(f"{name} exited with {code}" for name, code in ended.items())
      + "; stopped the rest."
    )
