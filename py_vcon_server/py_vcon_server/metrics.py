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
  all processors use the no-op decorator — zero overhead, no imports
  of prometheus_client.

  If install_instrumentation() is called but ENABLE_PROMETHEUS=False,
  ACTIVE_RUNS is still maintained and /diagnostics still works, but
  no Prometheus metrics are created.
"""

import time
import uuid
import functools
import typing
import logging

logger = logging.getLogger(__name__)

# ── Active runs registry ──────────────────────────────────────────────────────
# key:   run_id (str uuid)
# value: dict with keys:
#   processor_name  (str)
#   vcon_uuids      (list of str)
#   entry_point     (str)
#   pipeline_name   (str)
#   job_id          (str)
#   start_time      (float, epoch seconds)
#
# elapsed_seconds is NOT stored here — it is computed at query time
# in the /diagnostics endpoint so the value is always current.
ACTIVE_RUNS: typing.Dict[str, dict] = {}

# ── Prometheus metric objects ─────────────────────────────────────────────────
# All None until install_instrumentation() is called with ENABLE_PROMETHEUS=True.
_processor_active_gauge:    typing.Any = None  # prometheus_client.Gauge
_processor_duration_hist:   typing.Any = None  # prometheus_client.Histogram
_background_job_heartbeat:  typing.Any = None  # prometheus_client.Gauge

# ── Instrumentation state ─────────────────────────────────────────────────────
_INSTRUMENTATION_INSTALLED = False


# ── Decorator identity check ──────────────────────────────────────────────────

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


# ── No-op decorator ───────────────────────────────────────────────────────────

def _noop_decorator(func):
  """
  Identity decorator — returns func unchanged.
  Applied by register() when instrumentation is not yet installed,
  so that get_instrumentation_decorator() always returns a callable.
  """
  return func


# ── Instrumented decorator ────────────────────────────────────────────────────

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

    # Collect vCon UUIDs — best effort, don't let failures affect processing
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


# ── Public API ────────────────────────────────────────────────────────────────

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
  call.  Safe to call multiple times — subsequent calls are no-ops.

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
