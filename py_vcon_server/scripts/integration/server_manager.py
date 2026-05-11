# Copyright (C) 2023-2026 SIPez LLC.  All rights reserved.
"""
integration/server_manager.py -- Owns the py_vcon_server subprocess lifecycle.
"""

import os
import signal
import socket
import subprocess
import sys
import tempfile
import time
import urllib.parse


STARTUP_TIMEOUT = float(os.environ.get("INTEGRATION_STARTUP_TIMEOUT", "30"))
SHUTDOWN_TIMEOUT = float(os.environ.get("INTEGRATION_SHUTDOWN_TIMEOUT", "30"))
HEALTH_TIMEOUT = float(os.environ.get("INTEGRATION_HEALTH_TIMEOUT", "5"))


def port_is_free(port, host="localhost"):
  with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
    return s.connect_ex((host, port)) != 0


def wait_for_port_free(port, timeout=30.0):
  deadline = time.time() + timeout
  while time.time() < deadline:
    if port_is_free(port):
      return True
    time.sleep(0.5)
  return False


class ServerManager:
  """
  Manages the py_vcon_server subprocess for the duration of the
  integration test run.  Stages never interact with the subprocess
  directly -- they call is_healthy(), and the runner calls
  start()/stop()/restart() as needed between stages.
  """

  def __init__(self, base_url, env):
    self.base_url = base_url
    self.env = env
    self._port = int(urllib.parse.urlparse(base_url).port or 8000)
    self._proc = None
    self._log_file = None

  def start(self):
    """
    Start the py_vcon_server subprocess and wait for it to become healthy.
    Returns True if the server is healthy within STARTUP_TIMEOUT.
    """
    host = urllib.parse.urlparse(self.base_url).hostname or "localhost"
    if not port_is_free(self._port, host):
      print("  ERROR: port {} already in use before server start".format(
          self._port))
      return False

    self._log_file = tempfile.NamedTemporaryFile(
        prefix="py_vcon_server_integration_",
        suffix=".log",
        delete=False,
        mode="wb",
      )

    self._proc = subprocess.Popen(
        [sys.executable, "-m", "py_vcon_server"],
        env=self.env,
        stdout=self._log_file,
        stderr=subprocess.STDOUT,
      )

    ready = self._wait_for_healthy(STARTUP_TIMEOUT)
    if not ready:
      print("  Server did not become ready within {}s".format(STARTUP_TIMEOUT))
      print("  Log: {}".format(self._log_file.name))
      self._print_log_tail(20)
    return ready

  def stop(self):
    """
    Send SIGTERM to the server and wait for clean exit.
    Returns True if the process exited cleanly within SHUTDOWN_TIMEOUT.
    """
    if self._proc is None:
      return True

    if self._proc.poll() is not None:
      self._proc = None
      return True

    self._proc.send_signal(signal.SIGTERM)
    try:
      exitcode = self._proc.wait(timeout=SHUTDOWN_TIMEOUT)
      self._proc = None
      return exitcode == 0
    except subprocess.TimeoutExpired:
      self._proc.kill()
      self._proc.wait()
      self._proc = None
      return False

  def restart(self):
    """Stop the server if running, then start it again."""
    self.stop()
    if not wait_for_port_free(self._port):
      print("  Port {} still in use after stop -- cannot restart".format(
          self._port))
      return False
    return self.start()

  def is_healthy(self, timeout=None):
    """
    Return True if GET /docs responds with 200 within timeout seconds.
    """
    if timeout is None:
      timeout = HEALTH_TIMEOUT
    return self._wait_for_healthy(timeout)

  def log_path(self):
    if self._log_file:
      return self._log_file.name
    return None

  def pid(self):
    if self._proc:
      return self._proc.pid
    return None

  def poll(self):
    """Return process exit code if exited, None if still running."""
    if self._proc:
      return self._proc.poll()
    return None

  def _wait_for_healthy(self, timeout):
    import urllib.request
    import urllib.error

    deadline = time.time() + timeout
    while time.time() < deadline:
      if self._proc and self._proc.poll() is not None:
        return False  # process died
      try:
        with urllib.request.urlopen(
            "{}/docs".format(self.base_url), timeout=1.0
          ) as resp:
          if resp.status == 200:
            return True
      except Exception:
        pass
      time.sleep(0.3)
    return False

  def _print_log_tail(self, lines=20):
    if not self._log_file:
      return
    try:
      self._log_file.flush()
      with open(self._log_file.name, "rb") as f:
        content = f.read().decode("utf-8", errors="replace")
      tail = content.strip().split("\n")[-lines:]
      print("  --- server log tail ---")
      for line in tail:
        print("  {}".format(line))
    except Exception:
      pass
