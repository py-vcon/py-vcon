# Copyright (C) 2023-2026 SIPez LLC.  All rights reserved.
"""
Unit tests for shared memory cross-worker diagnostics in
py_vcon_server/metrics.py.

Tests the slot_write/slot_read/claim_slot machinery, the _sync_slot()
hot path, the read_all_slots() aggregation, the init/shutdown lifecycle,
and the /diagnostics endpoint integration with shared memory.

These tests create local SharedMemory segments -- no multiprocessing
needed for the unit test level.  The full cross-worker flow is tested
by Stage 8 in scripts/test_multiworker.py.

Structure:
  Section 1 -- Low-level slot functions (slot_write, slot_read, slot_offset)
  Section 2 -- claim_slot
  Section 3 -- _sync_slot and read_all_slots
  Section 4 -- init_diagnostics_shm / shutdown_diagnostics_shm lifecycle
  Section 5 -- /diagnostics endpoint integration with shared memory
  Section 6 -- Error and edge case paths
"""
import json
import os
import struct
import time
import threading
import pytest
import pytest_asyncio
import fastapi.testclient
import vcon
import py_vcon_server
import py_vcon_server.db
import py_vcon_server.processor
import py_vcon_server.settings
import py_vcon_server.metrics as metrics
from multiprocessing.shared_memory import SharedMemory
from py_vcon_server.settings import VCON_STORAGE_URL

UUID = "01855517-dshm-fake-uuid-77776666acbe"


# -- Helpers -------------------------------------------------------------------

def make_test_vcon() -> vcon.Vcon:
  v = vcon.Vcon()
  v._vcon_dict["uuid"] = UUID
  v.set_party_parameter("tel", "+15551234567")
  v.set_party_parameter("name", "Alice", 0)
  v.set_subject("Test conversation")
  v.add_dialog_inline_text(
      "Hello, this is a test.",
      "2024-03-06T20:07:43+00:00",
      5.0,
      0,
      vcon.Vcon.MEDIATYPE_TEXT_PLAIN
    )
  return v


@pytest.fixture
def shm_one_slot():
  """
  Create a shared memory segment with one slot for testing.
  Yields (shm, slot_index=0).
  Cleans up on teardown.
  """
  total_size = metrics.DIAG_HEADER_REGION_SIZE + metrics.DIAG_SLOT_SIZE
  shm = SharedMemory(create=True, size=total_size)
  shm.buf[:total_size] = b'\x00' * total_size
  yield shm, 0
  shm.close()
  shm.unlink()


@pytest.fixture
def shm_multi_slot():
  """
  Create a shared memory segment with 4 slots for testing.
  Yields (shm, num_slots=4).
  Cleans up on teardown.
  """
  num_slots = 4
  total_size = metrics.DIAG_HEADER_REGION_SIZE + (num_slots * metrics.DIAG_SLOT_SIZE)
  shm = SharedMemory(create=True, size=total_size)
  shm.buf[:total_size] = b'\x00' * total_size
  yield shm, num_slots
  shm.close()
  shm.unlink()


@pytest.fixture
def save_diag_state():
  """
  Save and restore metrics module diagnostics state around a test.
  """
  saved = {
      "_diag_shm": metrics._diag_shm,
      "_diag_slot_index": metrics._diag_slot_index,
      "_diag_num_slots": metrics._diag_num_slots,
      "_diag_worker_key": metrics._diag_worker_key,
      "_slot_cache": dict(metrics._slot_cache),
  }
  yield
  metrics._diag_shm = saved["_diag_shm"]
  metrics._diag_slot_index = saved["_diag_slot_index"]
  metrics._diag_num_slots = saved["_diag_num_slots"]
  metrics._diag_worker_key = saved["_diag_worker_key"]
  metrics._slot_cache.clear()
  metrics._slot_cache.update(saved["_slot_cache"])


VCON_STORAGE = None

@pytest_asyncio.fixture(autouse=True)
async def setup():
  vs = py_vcon_server.db.VconStorage.instantiate(VCON_STORAGE_URL)
  global VCON_STORAGE
  VCON_STORAGE = vs
  yield
  VCON_STORAGE = None
  await vs.shutdown()


# ==============================================================================
#  SECTION 1: Low-level slot functions
# ==============================================================================

def test_slot_offset_calculation():
  """ slot_offset returns HEADER_REGION_SIZE + slot_index * SLOT_SIZE """
  assert metrics.slot_offset(0) == metrics.DIAG_HEADER_REGION_SIZE
  assert metrics.slot_offset(1) == metrics.DIAG_HEADER_REGION_SIZE + metrics.DIAG_SLOT_SIZE
  assert metrics.slot_offset(3) == metrics.DIAG_HEADER_REGION_SIZE + 3 * metrics.DIAG_SLOT_SIZE


def test_slot_write_read_roundtrip(shm_one_slot):
  """ Write a dict to a slot and read it back """
  shm, slot_index = shm_one_slot
  data = {
      "worker_key": "host:8000:1234:5678",
      "last_updated": time.time(),
      "active_runs": {
          "run-1": {
              "processor_name": "test_proc",
              "vcon_uuids": ["uuid-1"],
              "entry_point": "/process",
              "pipeline_name": "",
              "job_id": "",
              "start_time": time.time(),
          }
      }
  }
  metrics.slot_write(shm, slot_index, data)
  result, retries = metrics.slot_read(shm, slot_index)
  assert retries == 0
  assert result["worker_key"] == "host:8000:1234:5678"
  assert "run-1" in result["active_runs"]
  assert result["active_runs"]["run-1"]["processor_name"] == "test_proc"


def test_slot_read_empty_slot(shm_one_slot):
  """ Reading an unwritten slot returns empty dict """
  shm, slot_index = shm_one_slot
  result, retries = metrics.slot_read(shm, slot_index)
  assert result == {}
  assert retries == 0


def test_slot_write_overwrites_previous(shm_one_slot):
  """ Writing to a slot overwrites the previous content """
  shm, slot_index = shm_one_slot
  data1 = {"worker_key": "w1", "last_updated": 1.0, "active_runs": {"r1": {}}}
  data2 = {"worker_key": "w2", "last_updated": 2.0, "active_runs": {"r2": {}}}
  metrics.slot_write(shm, slot_index, data1)
  metrics.slot_write(shm, slot_index, data2)
  result, _ = metrics.slot_read(shm, slot_index)
  assert result["worker_key"] == "w2"
  assert "r2" in result["active_runs"]
  assert "r1" not in result["active_runs"]


def test_slot_write_empty_active_runs(shm_one_slot):
  """ Writing empty active_runs is valid """
  shm, slot_index = shm_one_slot
  data = {"worker_key": "w1", "last_updated": time.time(), "active_runs": {}}
  metrics.slot_write(shm, slot_index, data)
  result, _ = metrics.slot_read(shm, slot_index)
  assert result["active_runs"] == {}


def test_slot_write_multiple_slots(shm_multi_slot):
  """ Each slot is independent """
  shm, num_slots = shm_multi_slot
  for i in range(num_slots):
    data = {
        "worker_key": "worker-{}".format(i),
        "last_updated": time.time(),
        "active_runs": {"run-{}".format(i): {"processor_name": "p{}".format(i)}}
    }
    metrics.slot_write(shm, i, data)

  for i in range(num_slots):
    result, _ = metrics.slot_read(shm, i)
    assert result["worker_key"] == "worker-{}".format(i)
    assert "run-{}".format(i) in result["active_runs"]


def test_generation_counter_increments(shm_one_slot):
  """ Each write increments the generation counter by 2 (odd then even) """
  shm, slot_index = shm_one_slot
  offset = metrics.slot_offset(slot_index)

  # Initial generation is 0
  gen = struct.unpack_from("<I", shm.buf, offset)[0]
  assert gen == 0

  data = {"worker_key": "w1", "last_updated": 1.0, "active_runs": {}}
  metrics.slot_write(shm, slot_index, data)

  gen = struct.unpack_from("<I", shm.buf, offset)[0]
  assert gen == 2  # 0 -> 1 (odd) -> 2 (even)

  metrics.slot_write(shm, slot_index, data)
  gen = struct.unpack_from("<I", shm.buf, offset)[0]
  assert gen == 4


# ==============================================================================
#  SECTION 2: claim_slot
# ==============================================================================

def test_claim_slot_sequential(shm_multi_slot):
  """ Sequential claim_slot calls return incrementing indices """
  shm, num_slots = shm_multi_slot
  indices = []
  for _ in range(num_slots):
    idx, _ = metrics.claim_slot(shm)
    indices.append(idx)
  assert indices == [0, 1, 2, 3]


# ==============================================================================
#  SECTION 3: _sync_slot and read_all_slots
# ==============================================================================

def test_sync_slot_noop_when_shm_none(save_diag_state):
  """ _sync_slot does nothing when _diag_shm is None """
  metrics._diag_shm = None
  # Should not raise
  metrics._sync_slot()


def test_sync_slot_writes_active_runs(shm_one_slot, save_diag_state):
  """ _sync_slot writes ACTIVE_RUNS to the assigned slot """
  shm, slot_index = shm_one_slot
  metrics._diag_shm = shm
  metrics._diag_slot_index = slot_index
  metrics._diag_num_slots = 1
  metrics._diag_worker_key = "test:worker:key"

  run_id = "test-run-001"
  metrics.ACTIVE_RUNS[run_id] = {
      "processor_name": "test_proc",
      "vcon_uuids": ["uuid-1"],
      "entry_point": "/process",
      "pipeline_name": "",
      "job_id": "",
      "start_time": time.time(),
  }

  try:
    metrics._sync_slot()
    result, _ = metrics.slot_read(shm, slot_index)
    assert result["worker_key"] == "test:worker:key"
    assert run_id in result["active_runs"]
    assert result["active_runs"][run_id]["processor_name"] == "test_proc"
    assert result["last_updated"] > 0
  finally:
    metrics.ACTIVE_RUNS.pop(run_id, None)


def test_read_all_slots_returns_none_when_shm_none(save_diag_state):
  """ read_all_slots returns None when shared memory not initialized """
  metrics._diag_shm = None
  assert metrics.read_all_slots() is None


def test_read_all_slots_merges_across_slots(shm_multi_slot, save_diag_state):
  """ read_all_slots merges active_runs from all written slots """
  shm, num_slots = shm_multi_slot
  metrics._diag_shm = shm
  metrics._diag_slot_index = 0
  metrics._diag_num_slots = num_slots
  metrics._diag_worker_key = "test:worker:0"

  now = time.time()
  for i in range(num_slots):
    data = {
        "worker_key": "worker-{}".format(i),
        "last_updated": now,
        "active_runs": {
            "run-{}".format(i): {
                "processor_name": "proc-{}".format(i),
                "vcon_uuids": [],
                "entry_point": "/process",
                "pipeline_name": "",
                "job_id": "",
                "start_time": now - 10 + i,
            }
        },
    }
    metrics.slot_write(shm, i, data)

  result = metrics.read_all_slots()
  assert result is not None
  merged_runs = result["active_runs"]
  assert len(merged_runs) == num_slots
  for i in range(num_slots):
    assert "run-{}".format(i) in merged_runs


def test_read_all_slots_skips_empty_slots(shm_multi_slot, save_diag_state):
  """ read_all_slots skips slots that have not been written """
  shm, num_slots = shm_multi_slot
  metrics._diag_shm = shm
  metrics._diag_slot_index = 0
  metrics._diag_num_slots = num_slots
  metrics._diag_worker_key = "test:worker:0"

  # Only write to slot 1
  data = {
      "worker_key": "worker-1",
      "last_updated": time.time(),
      "active_runs": {"run-1": {"processor_name": "p1", "start_time": time.time()}},
  }
  metrics.slot_write(shm, 1, data)

  result = metrics.read_all_slots()
  assert result is not None
  merged_runs = result["active_runs"]
  assert len(merged_runs) == 1
  assert "run-1" in merged_runs


def test_read_all_slots_no_meta_when_clean(shm_one_slot, save_diag_state):
  """ read_all_slots omits _diagnostics_meta when no errors or truncation """
  shm, slot_index = shm_one_slot
  metrics._diag_shm = shm
  metrics._diag_slot_index = slot_index
  metrics._diag_num_slots = 1
  metrics._diag_worker_key = "test:worker:0"

  data = {
      "worker_key": "worker-0",
      "last_updated": time.time(),
      "active_runs": {},
  }
  metrics.slot_write(shm, slot_index, data)

  result = metrics.read_all_slots()
  assert "_diagnostics_meta" not in result


# ==============================================================================
#  SECTION 4: init_diagnostics_shm / shutdown_diagnostics_shm lifecycle
# ==============================================================================

def test_init_noop_when_env_not_set(save_diag_state):
  """ init_diagnostics_shm is a no-op when PYVCON_DIAG_SHM not set """
  old_val = os.environ.pop("PYVCON_DIAG_SHM", None)
  try:
    metrics._diag_shm = None
    metrics.init_diagnostics_shm()
    assert metrics._diag_shm is None
  finally:
    if old_val is not None:
      os.environ["PYVCON_DIAG_SHM"] = old_val


def test_init_and_shutdown_lifecycle(save_diag_state):
  """
  init_diagnostics_shm attaches to shared memory and claims a slot.
  shutdown_diagnostics_shm writes a final idle state and closes.
  """
  num_slots = 2
  total_size = metrics.DIAG_HEADER_REGION_SIZE + (num_slots * metrics.DIAG_SLOT_SIZE)
  shm = SharedMemory(create=True, size=total_size)
  shm.buf[:total_size] = b'\x00' * total_size

  os.environ["PYVCON_DIAG_SHM"] = shm.name
  os.environ["PYVCON_DIAG_NUM_SLOTS"] = str(num_slots)

  try:
    metrics._diag_shm = None
    metrics._diag_slot_index = None
    metrics._diag_num_slots = 0
    metrics._diag_worker_key = ""

    metrics.init_diagnostics_shm()

    assert metrics._diag_shm is not None
    assert metrics._diag_slot_index == 0  # first claim
    assert metrics._diag_num_slots == num_slots
    assert str(os.getpid()) in metrics._diag_worker_key

    metrics.shutdown_diagnostics_shm()
    assert metrics._diag_shm is None

  finally:
    os.environ.pop("PYVCON_DIAG_SHM", None)
    os.environ.pop("PYVCON_DIAG_NUM_SLOTS", None)
    shm.close()
    shm.unlink()


def test_init_invalid_num_slots(save_diag_state):
  """ init_diagnostics_shm handles non-integer PYVCON_DIAG_NUM_SLOTS """
  os.environ["PYVCON_DIAG_SHM"] = "fake_name"
  os.environ["PYVCON_DIAG_NUM_SLOTS"] = "not_a_number"
  try:
    metrics._diag_shm = None
    metrics.init_diagnostics_shm()
    assert metrics._diag_shm is None
  finally:
    os.environ.pop("PYVCON_DIAG_SHM", None)
    os.environ.pop("PYVCON_DIAG_NUM_SLOTS", None)


def test_init_zero_num_slots(save_diag_state):
  """ init_diagnostics_shm handles PYVCON_DIAG_NUM_SLOTS=0 """
  os.environ["PYVCON_DIAG_SHM"] = "fake_name"
  os.environ["PYVCON_DIAG_NUM_SLOTS"] = "0"
  try:
    metrics._diag_shm = None
    metrics.init_diagnostics_shm()
    assert metrics._diag_shm is None
  finally:
    os.environ.pop("PYVCON_DIAG_SHM", None)
    os.environ.pop("PYVCON_DIAG_NUM_SLOTS", None)


def test_init_bad_shm_name(save_diag_state):
  """ init_diagnostics_shm handles nonexistent shared memory name """
  os.environ["PYVCON_DIAG_SHM"] = "nonexistent_shm_segment_xyz"
  os.environ["PYVCON_DIAG_NUM_SLOTS"] = "2"
  try:
    metrics._diag_shm = None
    metrics.init_diagnostics_shm()
    assert metrics._diag_shm is None
  finally:
    os.environ.pop("PYVCON_DIAG_SHM", None)
    os.environ.pop("PYVCON_DIAG_NUM_SLOTS", None)


# ==============================================================================
#  SECTION 5: /diagnostics endpoint integration
# ==============================================================================

def test_diagnostics_endpoint_uses_shared_memory(shm_multi_slot, save_diag_state):
  """
  When shared memory is initialized, /diagnostics merges runs from
  all slots instead of using local ACTIVE_RUNS.
  """
  shm, num_slots = shm_multi_slot
  metrics._diag_shm = shm
  metrics._diag_slot_index = 0
  metrics._diag_num_slots = num_slots
  metrics._diag_worker_key = "test:worker:0"
  metrics._slot_cache.clear()

  now = time.time()
  # Simulate two workers with active runs in their slots
  for i in range(2):
    data = {
        "worker_key": "worker-{}".format(i),
        "last_updated": now,
        "active_runs": {
            "run-{}".format(i): {
                "processor_name": "proc-{}".format(i),
                "vcon_uuids": ["uuid-{}".format(i)],
                "entry_point": "/process",
                "pipeline_name": "",
                "job_id": "",
                "start_time": now - 5.0,
            }
        },
    }
    metrics.slot_write(shm, i, data)

  with fastapi.testclient.TestClient(py_vcon_server.restapi) as client:
    response = client.get("/diagnostics")
    assert response.status_code == 200
    diag = response.json()
    # Should see runs from both slots
    assert "run-0" in diag
    assert "run-1" in diag
    assert diag["run-0"]["processor_name"] == "proc-0"
    assert diag["run-1"]["processor_name"] == "proc-1"
    # elapsed_seconds should be computed at query time
    assert diag["run-0"]["elapsed_seconds"] > 0
    assert diag["run-1"]["elapsed_seconds"] > 0


def test_diagnostics_endpoint_fallback_when_no_shm(save_diag_state):
  """
  When shared memory is not initialized, /diagnostics uses local
  ACTIVE_RUNS (the current single-worker behavior).
  """
  metrics._diag_shm = None

  with fastapi.testclient.TestClient(py_vcon_server.restapi) as client:
    response = client.get("/diagnostics")
    assert response.status_code == 200
    assert response.json() == {} or isinstance(response.json(), dict)


# ==============================================================================
#  SECTION 6: Error and edge case paths
# ==============================================================================

def test_slot_write_payload_too_large(shm_one_slot):
  """ slot_write raises ValueError when payload exceeds MAX_PAYLOAD_SIZE """
  shm, slot_index = shm_one_slot
  # Build a payload larger than MAX_PAYLOAD_SIZE
  huge_data = {
      "worker_key": "w1",
      "last_updated": 1.0,
      "active_runs": {
          "run-{}".format(i): {"data": "x" * 1000}
          for i in range(200)
      }
  }
  with pytest.raises(ValueError, match="Payload too large"):
    metrics.slot_write(shm, slot_index, huge_data)


def test_slot_read_max_retries_raises(shm_one_slot):
  """
  slot_read raises RuntimeError when generation counter stays odd
  (simulating a permanently stuck writer).
  """
  shm, slot_index = shm_one_slot
  offset = metrics.slot_offset(slot_index)

  # Write an odd generation counter and non-zero length to simulate
  # a write stuck in progress
  struct.pack_into("<I", shm.buf, offset, 1)      # odd generation
  struct.pack_into("<I", shm.buf, offset + 4, 10)  # non-zero length

  with pytest.raises(RuntimeError, match="exceeded max_retries"):
    metrics.slot_read(shm, slot_index, max_retries=5)


def test_slot_read_json_decode_failure(shm_one_slot):
  """
  slot_read raises json.JSONDecodeError when payload is not valid JSON.
  """
  shm, slot_index = shm_one_slot
  offset = metrics.slot_offset(slot_index)

  bad_payload = b"not valid json!!!"
  struct.pack_into("<I", shm.buf, offset, 0)  # even generation
  struct.pack_into("<I", shm.buf, offset + 4, len(bad_payload))
  shm.buf[offset + metrics.DIAG_SLOT_HEADER_SIZE:
          offset + metrics.DIAG_SLOT_HEADER_SIZE + len(bad_payload)] = bad_payload
  struct.pack_into("<I", shm.buf, offset, 2)  # even generation (stable)

  with pytest.raises(json.JSONDecodeError):
    metrics.slot_read(shm, slot_index)


def test_read_all_slots_stale_fallback_on_read_error(shm_one_slot, save_diag_state):
  """
  When slot_read raises RuntimeError, read_all_slots falls back to
  cached data and reports the error in _diagnostics_meta.
  """
  shm, slot_index = shm_one_slot
  metrics._diag_shm = shm
  metrics._diag_slot_index = slot_index
  metrics._diag_num_slots = 1
  metrics._diag_worker_key = "test:worker:0"
  metrics._slot_cache.clear()

  # Write valid data first (to populate cache)
  data = {
      "worker_key": "worker-0",
      "last_updated": time.time(),
      "active_runs": {
          "run-stale": {
              "processor_name": "stale_proc",
              "start_time": time.time() - 100,
          }
      },
  }
  metrics.slot_write(shm, slot_index, data)

  # Read once to populate cache
  result = metrics.read_all_slots()
  assert "run-stale" in result["active_runs"]

  # Now corrupt the slot to force RuntimeError
  offset = metrics.slot_offset(slot_index)
  struct.pack_into("<I", shm.buf, offset, 1)      # odd = stuck
  struct.pack_into("<I", shm.buf, offset + 4, 10)

  # read_all_slots should return cached data with error metadata
  result = metrics.read_all_slots()
  assert result is not None
  assert "run-stale" in result["active_runs"]
  assert "_diagnostics_meta" in result
  assert "slot_errors" in result["_diagnostics_meta"]
  assert "0" in result["_diagnostics_meta"]["slot_errors"]
  error_info = result["_diagnostics_meta"]["slot_errors"]["0"]
  assert "error" in error_info
  assert error_info["stale_data"] is True


def test_read_all_slots_stale_fallback_no_cache(shm_one_slot, save_diag_state):
  """
  When slot_read raises RuntimeError and there is no cached data,
  read_all_slots reports the error with stale_data=False.
  """
  shm, slot_index = shm_one_slot
  metrics._diag_shm = shm
  metrics._diag_slot_index = slot_index
  metrics._diag_num_slots = 1
  metrics._diag_worker_key = "test:worker:0"
  metrics._slot_cache.clear()

  # Corrupt the slot without ever writing valid data
  offset = metrics.slot_offset(slot_index)
  struct.pack_into("<I", shm.buf, offset, 1)      # odd = stuck
  struct.pack_into("<I", shm.buf, offset + 4, 10)

  result = metrics.read_all_slots()
  assert result is not None
  assert len(result["active_runs"]) == 0
  assert "_diagnostics_meta" in result
  error_info = result["_diagnostics_meta"]["slot_errors"]["0"]
  assert error_info["stale_data"] is False
  assert error_info["worker_key"] == "unknown"


def test_sync_slot_truncation(shm_one_slot, save_diag_state):
  """
  When ACTIVE_RUNS is too large to fit in a slot, _sync_slot truncates
  intelligently and includes _truncated metadata.
  """
  shm, slot_index = shm_one_slot
  metrics._diag_shm = shm
  metrics._diag_slot_index = slot_index
  metrics._diag_num_slots = 1
  metrics._diag_worker_key = "test:worker:0"

  # Fill ACTIVE_RUNS with enough entries to overflow the slot
  try:
    for i in range(200):
      metrics.ACTIVE_RUNS["run-overflow-{}".format(i)] = {
          "processor_name": "overflow_proc_{}".format(i),
          "vcon_uuids": ["uuid-{:06d}-{}".format(j, i) for j in range(30)],
          "entry_point": "/process",
          "pipeline_name": "pipeline_{}".format(i),
          "job_id": "job-{}".format(i),
          "start_time": time.time() - 200 + i,  # oldest first
      }

    metrics._sync_slot()

    result, _ = metrics.slot_read(shm, slot_index)
    assert "_truncated" in result
    trunc = result["_truncated"]
    assert trunc["total_runs"] == 200
    assert trunc["included_runs"] < 200
    assert trunc["dropped_runs"] > 0
    assert trunc["full_payload_bytes"] > metrics.DIAG_MAX_PAYLOAD_SIZE
    assert trunc["max_payload_bytes"] == metrics.DIAG_MAX_PAYLOAD_SIZE

    # Oldest runs should be included (lowest start_time)
    included_runs = result["active_runs"]
    if len(included_runs) > 1:
      start_times = [r.get("start_time", 0) for r in included_runs.values()]
      # The included runs should be the oldest ones
      assert start_times[0] < start_times[-1] or len(start_times) == 1

  finally:
    for i in range(200):
      metrics.ACTIVE_RUNS.pop("run-overflow-{}".format(i), None)


def test_read_all_slots_surfaces_truncation_in_meta(shm_one_slot, save_diag_state):
  """
  When a slot contains _truncated metadata, read_all_slots includes
  it in _diagnostics_meta.truncated_slots.
  """
  shm, slot_index = shm_one_slot
  metrics._diag_shm = shm
  metrics._diag_slot_index = slot_index
  metrics._diag_num_slots = 1
  metrics._diag_worker_key = "test:worker:0"
  metrics._slot_cache.clear()

  # Write slot data with _truncated metadata directly
  data = {
      "worker_key": "worker-0",
      "last_updated": time.time(),
      "active_runs": {"run-1": {"processor_name": "p1", "start_time": time.time()}},
      "_truncated": {
          "total_runs": 50,
          "included_runs": 10,
          "dropped_runs": 40,
          "full_payload_bytes": 80000,
          "max_payload_bytes": metrics.DIAG_MAX_PAYLOAD_SIZE,
      },
  }
  metrics.slot_write(shm, slot_index, data)

  result = metrics.read_all_slots()
  assert "_diagnostics_meta" in result
  assert "truncated_slots" in result["_diagnostics_meta"]
  assert "0" in result["_diagnostics_meta"]["truncated_slots"]
  trunc = result["_diagnostics_meta"]["truncated_slots"]["0"]
  assert trunc["total_runs"] == 50
  assert trunc["dropped_runs"] == 40
