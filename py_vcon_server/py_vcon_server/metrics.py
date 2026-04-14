# Copyright (C) 2023-2026 SIPez LLC.  All rights reserved.
"""
py_vcon_server/metrics.py

Processor instrumentation for py_vcon_server.

Provides:
  - ACTIVE_RUNS dict: real-time registry of currently running processor
    invocations, keyed by run_id.  Used by the /diagnostics endpoint.
  - Prometheus metrics (optional, only when ENABLE_PROMETHEUS=True and
    install_instrumentation() has been called).
  - Decorator-based instrumentation applied to VconProcessor.process()
    at registration time via VconProcessorRegistry.register().

Usage:
  At server lifespan startup, call install_instrumentation() once.
  This initializes Prometheus metrics (if enabled) and ensures all
  already-registered processors are wrapped with the instrumented
  decorator.  Processors registered after this call are wrapped
  automatically by VconProcessorRegistry.register().

  In run_background_jobs(), call update_background_job_heartbeat()
  each loop iteration to update the background job liveness metric.

No-op behaviour:
  If install_instrumentation() is never called (e.g. CLI, unit tests),
  all processors use the no-op decorator - zero overhead, no imports
  of prometheus_client.

  If install_instrumentation() is called but ENABLE_PROMETHEUS=False,
  ACTIVE_RUNS is still maintained and /diagnostics still works, but
  no Prometheus metrics are created.
"""

import json
import os
import struct
import time
import uuid
import functools
import typing
import logging

logger = logging.getLogger(__name__)

# ------ Active runs registry -------------------------------------------------
# key:   run_id (str uuid)
# value: dict with keys:
#   processor_name  (str)
#   vcon_uuids      (list of str)
#   entry_point     (str)
#   pipeline_name   (str)
#   job_id          (str)
#   start_time      (float, epoch seconds)
#
# elapsed_seconds is NOT stored here - it is computed at query time
# in the /diagnostics endpoint so the value is always current.
ACTIVE_RUNS: typing.Dict[str, dict] = {}

# ------ Prometheus metric objects --------------------------------------------
# All None until install_instrumentation() is called with ENABLE_PROMETHEUS=True.
_processor_active_gauge:    typing.Any = None  # prometheus_client.Gauge
_processor_duration_hist:   typing.Any = None  # prometheus_client.Histogram
_background_job_heartbeat:  typing.Any = None  # prometheus_client.Gauge

# ------ Instrumentation state ------------------------------------------------
_INSTRUMENTATION_INSTALLED = False

# ------ Shared memory diagnostics state --------------------------------------
# Set by init_diagnostics_shm() at lifespan startup when PYVCON_DIAG_SHM
# env var is present (multi-worker mode).  None in single-worker mode.
_diag_shm: typing.Any = None              # SharedMemory handle
_diag_slot_index: typing.Union[int, None] = None  # this worker's slot
_diag_num_slots: int = 0                   # total slots (= NUM_RESTAPI_WORKERS)
_diag_worker_key: str = ""                 # cached worker_key for slot payloads
_slot_cache: typing.Dict[int, dict] = {}   # per-slot cache for stale fallback

# ------ Shared memory layout constants ---------------------------------------
# Matches the layout proven in scripts/test_shared_memory_poc.py.
#
# Segment layout:
#   Bytes 0-7:   header region (slot claim counter uint32 + reserved)
#   Bytes 8+:    N slots, each DIAG_SLOT_SIZE bytes
#
# Per-slot layout:
#   Bytes 0-3:   generation counter (uint32, little-endian)
#                even = stable/readable, odd = write in progress
#   Bytes 4-7:   payload length (uint32, little-endian)
#   Bytes 8+:    JSON payload (UTF-8), zero-padded
#
DIAG_SLOT_SIZE        = 64 * 1024   # 64 KB per worker
DIAG_SLOT_HEADER_SIZE = 8           # 4 bytes generation + 4 bytes length
DIAG_MAX_PAYLOAD_SIZE = DIAG_SLOT_SIZE - DIAG_SLOT_HEADER_SIZE
DIAG_HEADER_REGION_SIZE = 8         # segment header: claim counter + reserved


# ------ Shared memory slot functions -----------------------------------------
# These are direct copies of the functions proven in
# scripts/test_shared_memory_poc.py, kept self-contained in metrics.py
# to avoid import dependencies.

def slot_offset(slot_index: int) -> int:
  """ Return byte offset of slot_index in shared memory """
  return DIAG_HEADER_REGION_SIZE + (slot_index * DIAG_SLOT_SIZE)


def slot_write(shm, slot_index: int, data: dict) -> None:
  """
  Write data dict to slot using generation counter protocol.
  Increments counter to odd before write, even after.
  Single writer per slot --- no write-write races by design.
  """
  offset = slot_offset(slot_index)
  payload = json.dumps(data).encode("utf-8")
  if len(payload) > DIAG_MAX_PAYLOAD_SIZE:
    raise ValueError("Payload too large: {} > {}".format(
        len(payload), DIAG_MAX_PAYLOAD_SIZE))

  buf = shm.buf

  # Increment to odd --- signals write in progress to readers
  gen = struct.unpack_from("<I", buf, offset)[0]
  gen_odd = (gen & ~1) + 1   # round down to even, add 1 to make odd
  struct.pack_into("<I", buf, offset, gen_odd)

  # Write payload length and data
  struct.pack_into("<I", buf, offset + 4, len(payload))
  buf[offset + DIAG_SLOT_HEADER_SIZE:
      offset + DIAG_SLOT_HEADER_SIZE + len(payload)] = payload

  # Increment to next even --- signals write complete
  struct.pack_into("<I", buf, offset, gen_odd + 1)


def slot_read(shm, slot_index: int, max_retries: int = 100) -> tuple:
  """
  Read data dict from slot using generation counter protocol.
  Returns (data_dict, retry_count).
  Retries if a write is in progress or generation changed mid-read.
  Returns ({}, 0) if slot not yet written.
  Raises RuntimeError if max_retries exceeded.
  Raises json.JSONDecodeError if payload is corrupt.
  """
  offset = slot_offset(slot_index)
  buf = shm.buf
  retries = 0

  for attempt in range(max_retries):
    gen_before = struct.unpack_from("<I", buf, offset)[0]

    # Odd generation means write in progress --- spin
    if gen_before & 1:
      retries += 1
      time.sleep(0.000001)
      continue

    length = struct.unpack_from("<I", buf, offset + 4)[0]

    if length == 0:
      return ({}, retries)  # slot not yet written

    payload_bytes = bytes(
        buf[offset + DIAG_SLOT_HEADER_SIZE:
            offset + DIAG_SLOT_HEADER_SIZE + length]
      )

    gen_after = struct.unpack_from("<I", buf, offset)[0]

    if gen_before == gen_after:
      # Generation stable across read --- data is consistent
      return (json.loads(payload_bytes.decode("utf-8")), retries)

    # Generation changed mid-read --- retry
    retries += 1
    time.sleep(0.000001)

  raise RuntimeError(
      "slot_read: exceeded max_retries ({}) on slot {}".format(
          max_retries, slot_index)
    )


def claim_slot(shm) -> tuple:
  """
  Claim the next available slot index using fcntl.lockf for mutual exclusion.
  Safe across processes on both x86 and ARM.
  Called once per worker at startup --- not on the hot path.
  Returns (slot_index, was_contended).

  Note: uses shm._fd which is a CPython implementation detail available
  on Linux and macOS.
  """
  import fcntl

  fd = shm._fd
  was_contended = False

  try:
    fcntl.lockf(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
  except BlockingIOError:
    was_contended = True
    fcntl.lockf(fd, fcntl.LOCK_EX)

  try:
    slot_index = struct.unpack_from("<I", shm.buf, 0)[0]
    struct.pack_into("<I", shm.buf, 0, slot_index + 1)
  finally:
    fcntl.lockf(fd, fcntl.LOCK_UN)

  return slot_index, was_contended


# ------ Shared memory sync (hot path) ----------------------------------------

def _sync_slot() -> None:
  """
  Write current ACTIVE_RUNS to this worker's shared memory slot.
  Called synchronously from _instrumented_decorator on every
  ACTIVE_RUNS mutation.  No-op when shared memory is not initialized.

  If the payload exceeds DIAG_MAX_PAYLOAD_SIZE, truncates intelligently:
  keeps the oldest runs (most likely to be stuck) and includes _truncated
  metadata in the slot payload.
  """
  if _diag_shm is None:
    return

  data = {
      "worker_key": _diag_worker_key,
      "last_updated": time.time(),
      "active_runs": dict(ACTIVE_RUNS),
  }

  payload = json.dumps(data).encode("utf-8")

  if len(payload) <= DIAG_MAX_PAYLOAD_SIZE:
    slot_write(_diag_shm, _diag_slot_index, data)
    return

  # ------ Truncation path (error --- should be extremely rare) ---------------
  full_size = len(payload)
  total_runs = len(ACTIVE_RUNS)

  # Sort by start_time ascending --- keep oldest (most likely stuck)
  sorted_runs = sorted(
      ACTIVE_RUNS.items(),
      key=lambda item: item[1].get("start_time", 0)
    )

  # Build truncated payload incrementally
  truncated_runs = {}
  for run_id, run in sorted_runs:
    candidate = {
        "worker_key": _diag_worker_key,
        "last_updated": data["last_updated"],
        "active_runs": dict(truncated_runs),
        "_truncated": {
            "total_runs": total_runs,
            "included_runs": len(truncated_runs) + 1,
            "dropped_runs": total_runs - len(truncated_runs) - 1,
            "full_payload_bytes": full_size,
            "max_payload_bytes": DIAG_MAX_PAYLOAD_SIZE,
        },
    }
    candidate["active_runs"][run_id] = run
    test_payload = json.dumps(candidate).encode("utf-8")
    if len(test_payload) > DIAG_MAX_PAYLOAD_SIZE:
      break
    truncated_runs[run_id] = run

  data["active_runs"] = truncated_runs
  data["_truncated"] = {
      "total_runs": total_runs,
      "included_runs": len(truncated_runs),
      "dropped_runs": total_runs - len(truncated_runs),
      "full_payload_bytes": full_size,
      "max_payload_bytes": DIAG_MAX_PAYLOAD_SIZE,
  }

  try:
    slot_write(_diag_shm, _diag_slot_index, data)
  except ValueError:
    logger.error(
        "metrics: diagnostics slot envelope exceeds max payload "
        "for slot {}".format(_diag_slot_index)
      )
    return

  logger.error(
      "metrics: diagnostics payload truncated for slot {}: "
      "{} runs total, {} included, {} dropped "
      "(payload {} bytes > {} max)".format(
          _diag_slot_index, total_runs,
          len(truncated_runs),
          total_runs - len(truncated_runs),
          full_size, DIAG_MAX_PAYLOAD_SIZE)
    )


# ------ Shared memory read (query path) --------------------------------------

def read_all_slots():
  """
  Read all shared memory slots and merge active_runs dicts.
  Returns a dict with:
    - "active_runs": merged dict of all active runs across all workers
    - "_diagnostics_meta": (only if errors or truncation) slot-level issues
  Returns None if shared memory is not initialized (signals fallback
  to local ACTIVE_RUNS).
  """
  if _diag_shm is None:
    return None

  merged_runs = {}
  slot_errors = {}
  truncated_slots = {}

  for i in range(_diag_num_slots):
    try:
      slot_data, retries = slot_read(_diag_shm, i, max_retries=100)
      if slot_data:
        # Update cache on successful read
        _slot_cache[i] = slot_data
        merged_runs.update(slot_data.get("active_runs", {}))
        # Check for truncation metadata
        trunc = slot_data.get("_truncated")
        if trunc:
          truncated_slots[str(i)] = trunc

    except (RuntimeError, json.JSONDecodeError) as e:
      # Fall back to cached data for this slot
      logger.warning(
          "metrics: slot_read failed for slot {}: {}".format(i, e)
        )
      cached = _slot_cache.get(i)
      if cached:
        merged_runs.update(cached.get("active_runs", {}))
        slot_errors[str(i)] = {
            "error": str(e),
            "stale_data": True,
            "worker_key": cached.get("worker_key", "unknown"),
        }
      else:
        slot_errors[str(i)] = {
            "error": str(e),
            "stale_data": False,
            "worker_key": "unknown",
        }

  result = {"active_runs": merged_runs}

  # Only include _diagnostics_meta if there are issues
  if slot_errors or truncated_slots:
    meta = {"slot_count": _diag_num_slots, "slots_read": _diag_num_slots}
    if slot_errors:
      meta["slot_errors"] = slot_errors
    if truncated_slots:
      meta["truncated_slots"] = truncated_slots
    result["_diagnostics_meta"] = meta

  return result


# ------ Shared memory lifecycle ----------------------------------------------

def init_diagnostics_shm() -> None:
  """
  Attach to the shared memory segment allocated by __main__.py and
  claim a slot.  No-op if PYVCON_DIAG_SHM env var is not set.
  Called from lifespan startup.
  """
  global _diag_shm, _diag_slot_index, _diag_num_slots, _diag_worker_key

  shm_name = os.environ.get("PYVCON_DIAG_SHM", "")
  if not shm_name:
    logger.debug("metrics: PYVCON_DIAG_SHM not set, "
        "diagnostics will use local ACTIVE_RUNS only")
    return

  num_slots_str = os.environ.get("PYVCON_DIAG_NUM_SLOTS", "0")
  try:
    num_slots = int(num_slots_str)
  except ValueError:
    logger.error("metrics: PYVCON_DIAG_NUM_SLOTS invalid: {}".format(
        num_slots_str))
    return

  if num_slots <= 0:
    logger.error("metrics: PYVCON_DIAG_NUM_SLOTS must be > 0, got {}".format(
        num_slots))
    return

  try:
    from multiprocessing.shared_memory import SharedMemory
    shm = SharedMemory(name=shm_name, create=False)
  except Exception as e:
    logger.error(
        "metrics: failed to attach to shared memory '{}': {}".format(
            shm_name, e)
      )
    return

  try:
    slot_index, was_contended = claim_slot(shm)
  except Exception as e:
    logger.error("metrics: failed to claim diagnostics slot: {}".format(e))
    shm.close()
    return

  # Build worker_key --- use SERVER_STATE if available, else fallback
  try:
    import py_vcon_server.states
    if py_vcon_server.states.SERVER_STATE is not None:
      worker_key = py_vcon_server.states.SERVER_STATE.worker_key()
    else:
      worker_key = "unknown:{}".format(os.getpid())
  except Exception:
    worker_key = "unknown:{}".format(os.getpid())

  _diag_shm = shm
  _diag_slot_index = slot_index
  _diag_num_slots = num_slots
  _diag_worker_key = worker_key

  # Write initial idle state
  _sync_slot()

  logger.info(
      "metrics: diagnostics shared memory initialized "
      "shm={} slot={}/{} worker_key={} contended={}".format(
          shm_name, slot_index, num_slots, worker_key, was_contended)
    )


def shutdown_diagnostics_shm() -> None:
  """
  Write a final idle state to this worker's slot and close the
  shared memory handle.  Does not unlink --- the parent process does that.
  Called from lifespan shutdown.
  """
  global _diag_shm, _diag_slot_index, _diag_num_slots, _diag_worker_key

  if _diag_shm is None:
    return

  # Write final idle state so /diagnostics does not show stale runs
  try:
    slot_write(_diag_shm, _diag_slot_index, {
        "worker_key": _diag_worker_key,
        "last_updated": time.time(),
        "active_runs": {},
      })
  except Exception as e:
    logger.warning(
        "metrics: failed to write final idle state to slot {}: {}".format(
            _diag_slot_index, e)
      )

  try:
    _diag_shm.close()
  except Exception as e:
    logger.warning(
        "metrics: failed to close diagnostics shared memory: {}".format(e)
      )

  _diag_shm = None
  _diag_slot_index = None
  _diag_num_slots = 0
  _diag_worker_key = ""
  _slot_cache.clear()
  logger.info("metrics: diagnostics shared memory shut down")


# ------ Decorator identity check ---------------------------------------------

def is_instrumented(process_method) -> bool:
  """
  Return True if process_method has already been wrapped by
  _instrumented_decorator.

  Works by checking the __instrumentation_decorator__ attribute stamped
  onto every wrapper produced by _instrumented_decorator.  This avoids
  double-wrapping when install_instrumentation() re-wraps already-registered
  processors and when register() wraps newly registered processors.
  """
  return getattr(process_method, "__instrumentation_decorator__", None) is _instrumented_decorator


# ------ No-op decorator ------------------------------------------------------

def _noop_decorator(func):
  """
  Identity decorator - returns func unchanged.
  Applied by register() when instrumentation is not yet installed,
  so that get_instrumentation_decorator() always returns a callable.
  """
  return func


# ------ Instrumented decorator -----------------------------------------------

def _instrumented_decorator(func):
  """
  Wraps a VconProcessor.process() method with:
    - ACTIVE_RUNS registration (always, regardless of Prometheus)
    - Prometheus gauge inc/dec for active count (if enabled)
    - Prometheus histogram observation for duration (if enabled)
    - Structured log lines on start and finish (always)

  The wrapper stamps itself with __instrumentation_decorator__ = _instrumented_decorator
  so that is_instrumented() can detect it without a separate flag.
  """
  @functools.wraps(func)
  async def wrapper(self, processor_input, options):
    import py_vcon_server.processor as _proc

    run_id = str(uuid.uuid4())
    context = processor_input.get_run_context()
    processor_name = getattr(self, "_processor_name", self.__class__.__name__)
    entry_point = context.get(_proc.RUN_CONTEXT_ENTRY_POINT, "")
    pipeline_name = context.get(_proc.RUN_CONTEXT_PIPELINE_NAME, "")
    job_id = context.get(_proc.RUN_CONTEXT_JOB_ID, "")

    # Collect vCon UUIDs - best effort, don't let failures affect processing
    vcon_uuids = []
    try:
      for i in range(processor_input.num_vcons()):
        v = processor_input._vcons[i]
        if v is not None:
          uid = await v.get_vcon(_proc.VconTypes.UUID)
          if uid:
            vcon_uuids.append(uid)
    except Exception as e:
      logger.debug("metrics: could not collect vcon UUIDs: {}".format(e))

    # Register in ACTIVE_RUNS
    ACTIVE_RUNS[run_id] = {
        "processor_name": processor_name,
        "vcon_uuids":     vcon_uuids,
        "entry_point":    entry_point,
        "pipeline_name":  pipeline_name,
        "job_id":         job_id,
        "start_time":     time.time(),
      }

    # Sync to shared memory slot (no-op in single-worker mode)
    try:
      _sync_slot()
    except Exception as e:
      logger.debug("metrics: _sync_slot failed on run start: {}".format(e))

    # Prometheus active gauge increment

    if _processor_active_gauge is not None:
      try:
        _processor_active_gauge.labels(
            processor_name=processor_name,
            entry_point=entry_point
          ).inc()
      except Exception as e:
        logger.debug("metrics: gauge inc failed: {}".format(e))

    # Structured log on start
    logger.info("processor_started processor_name={} entry_point={} pipeline_name={} job_id={} vcon_uuids={} run_id={}".format(
        processor_name, entry_point, pipeline_name, job_id, vcon_uuids, run_id
      ))

    start = time.time()
    status = "success"
    try:
      return await func(self, processor_input, options)

    except Exception:
      status = "error"
      raise

    finally:
      elapsed = time.time() - start

      # Remove from ACTIVE_RUNS
      ACTIVE_RUNS.pop(run_id, None)

      # Sync to shared memory slot (no-op in single-worker mode)
      try:
        _sync_slot()
      except Exception as e:
        logger.debug("metrics: _sync_slot failed on run end: {}".format(e))

      # Prometheus active gauge decrement
      if _processor_active_gauge is not None:
        try:
          _processor_active_gauge.labels(
              processor_name=processor_name,
              entry_point=entry_point
            ).dec()
        except Exception as e:
          logger.debug("metrics: gauge dec failed: {}".format(e))

      # Prometheus duration histogram
      if _processor_duration_hist is not None:
        try:
          _processor_duration_hist.labels(
              processor_name=processor_name,
              entry_point=entry_point,
              status=status
            ).observe(elapsed)
        except Exception as e:
          logger.debug("metrics: histogram observe failed: {}".format(e))

      # Structured log on finish
      logger.info("processor_completed processor_name={} run_id={} elapsed_seconds={:.3f} status={}".format(
          processor_name, run_id, elapsed, status
        ))

  # Stamp the wrapper so is_instrumented() can identify it
  wrapper.__instrumentation_decorator__ = _instrumented_decorator
  return wrapper


# ------ Public API -----------------------------------------------------------

def get_instrumentation_decorator():
  """
  Return the currently active instrumentation decorator.

  Returns _instrumented_decorator if install_instrumentation() has been
  called, otherwise returns _noop_decorator.

  Called by VconProcessorRegistry.register() when wrapping newly
  registered processors.
  """
  if _INSTRUMENTATION_INSTALLED:
    return _instrumented_decorator
  return _noop_decorator


def install_instrumentation():
  """
  Activate processor instrumentation.

  Must be called at server lifespan startup, after plugin loading
  (so all processors are registered) and before the first processor
  call.  Safe to call multiple times - subsequent calls are no-ops.

  Effects:
    1. Sets _INSTRUMENTATION_INSTALLED = True so get_instrumentation_decorator()
       returns _instrumented_decorator for all future register() calls.
    2. Initializes Prometheus metrics if ENABLE_PROMETHEUS=True.
    3. Re-wraps all already-registered processors that are not yet wrapped.
  """
  global _INSTRUMENTATION_INSTALLED
  global _processor_active_gauge, _processor_duration_hist, _background_job_heartbeat

  if _INSTRUMENTATION_INSTALLED:
    return

  _INSTRUMENTATION_INSTALLED = True

  # Initialize Prometheus metrics if enabled
  import py_vcon_server.settings
  if py_vcon_server.settings.ENABLE_PROMETHEUS:
    # Ensure PROMETHEUS_MULTIPROC_DIR is set before prometheus_client
    # is imported. __main__.py sets this before workers start. If we
    # reach here without it set (e.g. tests, CLI), create a temp dir
    # with a warning.
    import os as _os
    if not _os.environ.get("PROMETHEUS_MULTIPROC_DIR", ""):
      import tempfile
      _fallback_dir = tempfile.mkdtemp(prefix="pyvcon_prom_fallback_")
      _os.environ["PROMETHEUS_MULTIPROC_DIR"] = _fallback_dir
      logger.warning(
          "metrics: PROMETHEUS_MULTIPROC_DIR was not set before "
          "install_instrumentation() was called. This means the server "
          "did not set it up via __main__.py (expected in production). "
          "Created fallback directory: {}. This directory will NOT be "
          "cleaned up automatically.".format(_fallback_dir)
        )

    try:
      import prometheus_client

      # Use registry.get_sample_value to check if metrics already exist
      # in the global registry. If they do, retrieve the existing collector
      # rather than creating a new one (which would raise ValueError).
      registry = prometheus_client.REGISTRY

      # Helper to get or create a metric
      def _get_or_create(metric_name, creator_fn):
        # Check if already registered by looking for it in the registry
        for collector in list(registry._names_to_collectors.values()):
          if hasattr(collector, "_name") and collector._name == metric_name:
            return collector
        return creator_fn()

      _processor_active_gauge = _get_or_create(
          "py_vcon_server_processor_active",
          lambda: prometheus_client.Gauge(
              "py_vcon_server_processor_active",
              "Number of currently running processor invocations",
              ["processor_name", "entry_point"]
            )
        )
      _processor_duration_hist = _get_or_create(
          "py_vcon_server_processor_duration_seconds",
          lambda: prometheus_client.Histogram(
              "py_vcon_server_processor_duration_seconds",
              "Processor execution time in seconds",
              ["processor_name", "entry_point", "status"],
              buckets=[1, 5, 15, 30, 60, 120, 300, 600, 1200, 1800]
            )
        )
      _background_job_heartbeat = _get_or_create(
          "py_vcon_server_background_job_heartbeat_timestamp",
          lambda: prometheus_client.Gauge(
              "py_vcon_server_background_job_heartbeat_timestamp",
              "Epoch timestamp of last background job loop iteration"
            )
        )
      logger.info("metrics: Prometheus processor metrics initialized")
    except Exception as e:
      logger.warning("metrics: failed to initialize Prometheus metrics: {}".format(e))

  # Re-wrap all already-registered processors that are not yet instrumented.
  # This handles processors registered before install_instrumentation() was called
  # (i.e. all processors loaded at module import time via PLUGIN_PATHS).
  try:
    import py_vcon_server.processor
    wrapped_count = 0
    for name, registration in py_vcon_server.processor.VCON_PROCESSOR_REGISTRY.items():
      if registration._processor_instance is not None:
        cls = type(registration._processor_instance)
        if not is_instrumented(cls.process):
          cls.process = _instrumented_decorator(cls.process)
          wrapped_count += 1
    logger.info("metrics: instrumentation installed, wrapped {} processors".format(wrapped_count))
  except Exception as e:
    logger.warning("metrics: failed to wrap existing processors: {}".format(e))


def update_background_job_heartbeat():
  """
  Update the background job loop liveness metric.
  Call this each iteration of run_background_jobs().
  No-op if Prometheus is not enabled or instrumentation not installed.
  """
  if _background_job_heartbeat is not None:
    try:
      _background_job_heartbeat.set(time.time())
    except Exception as e:
      logger.debug("metrics: background job heartbeat update failed: {}".format(e))
