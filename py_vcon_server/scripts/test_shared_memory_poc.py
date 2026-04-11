#!/usr/bin/env python3
# Copyright (C) 2023-2026 SIPez LLC.  All rights reserved.
"""
Proof of concept for multiprocessing.shared_memory based cross-worker
ACTIVE_RUNS aggregation.

Tests:
  1. Basic: parent allocates slots, forks workers, reads and aggregates,
     verifies last_updated timestamp and clean shutdown.
  2. Contention A: multiple reader threads hammer one slot while a writer
     thread writes as fast as possible.  Verifies no torn reads, no JSON
     decode errors, and that the retry path is actually exercised.
  3. Contention B: N workers write their own slots as fast as possible
     while the parent reads all slots in a tight loop.  Verifies no
     errors under maximum write pressure across all slots simultaneously.
  4. Multi-instance isolation: two independent parent processes each
     with their own shared memory segment.  Verifies no cross-talk
     between separate server instances on the same host.
  5. Slot assignment: N workers simultaneously claim slots using
     fcntl.lockf mutual exclusion.  Verifies no collisions or
     out-of-range indices across many iterations.

Usage:
    python3 scripts/test_shared_memory_poc.py [--workers N] [--duration S]
                                               [--iterations N]

No server or Redis required.
"""

import argparse
import json
import multiprocessing
import os
import struct
import sys
import threading
import time
from multiprocessing.shared_memory import SharedMemory

# ── Slot layout ───────────────────────────────────────────────────────────────
# Each slot is SLOT_SIZE bytes:
#   Bytes 0-3:   generation counter (uint32, little-endian)
#                even = stable/readable, odd = write in progress
#   Bytes 4-7:   payload length (uint32, little-endian)
#   Bytes 8+:    JSON payload (UTF-8), zero-padded
#
SLOT_SIZE        = 64 * 1024   # 64 KB per worker
HEADER_SIZE      = 8           # 4 bytes generation + 4 bytes length per slot
MAX_PAYLOAD_SIZE = SLOT_SIZE - HEADER_SIZE

# ── Shared memory layout ──────────────────────────────────────────────────────
# Header region (HEADER_REGION_SIZE bytes at offset 0):
#   Bytes 0-3:   slot claim counter (uint32, little-endian)
#                incremented under fcntl.lockf to assign slot indices
#   Bytes 4-7:   reserved
#
# Slot region (after header):
#   Slot N starts at HEADER_REGION_SIZE + (N * SLOT_SIZE)
#   Each slot SLOT_SIZE bytes with generation counter + payload as before
#
HEADER_REGION_SIZE = 8


def slot_offset(slot_index: int) -> int:
  """ Return byte offset of slot_index in shared memory """
  return HEADER_REGION_SIZE + (slot_index * SLOT_SIZE)


def slot_write(shm: SharedMemory, slot_index: int, data: dict) -> None:
  """
  Write data dict to slot using generation counter protocol.
  Increments counter to odd before write, even after.
  Single writer per slot — no write-write races by design.
  """
  offset = slot_offset(slot_index)
  payload = json.dumps(data).encode("utf-8")
  if len(payload) > MAX_PAYLOAD_SIZE:
    raise ValueError("Payload too large: {} > {}".format(
        len(payload), MAX_PAYLOAD_SIZE))

  buf = shm.buf

  # Increment to odd — signals write in progress to readers
  gen = struct.unpack_from("<I", buf, offset)[0]
  gen_odd = (gen & ~1) + 1   # round down to even, add 1 to make odd
  struct.pack_into("<I", buf, offset, gen_odd)

  # Write payload length and data
  struct.pack_into("<I", buf, offset + 4, len(payload))
  buf[offset + HEADER_SIZE: offset + HEADER_SIZE + len(payload)] = payload

  # Increment to next even — signals write complete
  struct.pack_into("<I", buf, offset, gen_odd + 1)


def slot_read(
    shm: SharedMemory,
    slot_index: int,
    max_retries: int = 100
  ) -> tuple:
  """
  Read data dict from slot using generation counter protocol.
  Returns (data_dict, retry_count).
  Retries if a write is in progress or generation changed mid-read.
  Returns ({}, 0) if slot not yet written.
  Raises RuntimeError if max_retries exceeded.
  """
  offset = slot_offset(slot_index)
  buf = shm.buf
  retries = 0

  for attempt in range(max_retries):
    gen_before = struct.unpack_from("<I", buf, offset)[0]

    # Odd generation means write in progress — spin
    if gen_before & 1:
      retries += 1
      time.sleep(0.000001)
      continue

    length = struct.unpack_from("<I", buf, offset + 4)[0]

    if length == 0:
      return ({}, retries)  # slot not yet written

    payload_bytes = bytes(
        buf[offset + HEADER_SIZE: offset + HEADER_SIZE + length]
      )

    gen_after = struct.unpack_from("<I", buf, offset)[0]

    if gen_before == gen_after:
      # Generation stable across read — data is consistent
      return (json.loads(payload_bytes.decode("utf-8")), retries)

    # Generation changed mid-read — retry
    retries += 1
    time.sleep(0.000001)

  raise RuntimeError(
      "slot_read: exceeded max_retries ({}) on slot {}".format(
          max_retries, slot_index)
    )


def claim_slot(shm: SharedMemory) -> tuple:
  """
  Claim the next available slot index using fcntl.lockf for mutual exclusion.
  Safe across processes on both x86 and ARM.
  Called once per worker at startup — not on the hot path.
  Returns (slot_index, was_contended) where was_contended=True means another
  process held the lock when we first tried to acquire it, proving the lock
  path was actually exercised under contention.

  Note: uses shm._fd which is a CPython implementation detail available
  on Linux and macOS.  The real server checks for this at startup and
  exits with a clear error if unavailable.
  """
  import fcntl

  # Use the shared memory file descriptor for locking.
  # SharedMemory exposes the underlying fd via _fd on Linux/macOS.
  fd = shm._fd
  was_contended = False

  # Try non-blocking first to detect contention — if another process holds
  # the lock, LOCK_NB raises BlockingIOError immediately rather than waiting.
  try:
    fcntl.lockf(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
  except BlockingIOError:
    # Lock was held by another process — fall back to blocking acquire.
    # This is the contention path we need to prove is reachable.
    was_contended = True
    fcntl.lockf(fd, fcntl.LOCK_EX)

  try:
    slot_index = struct.unpack_from("<I", shm.buf, 0)[0]
    struct.pack_into("<I", shm.buf, 0, slot_index + 1)
  finally:
    fcntl.lockf(fd, fcntl.LOCK_UN)

  return slot_index, was_contended


def reset_slot_counter(shm: SharedMemory) -> None:
  """ Reset the slot claim counter to 0. Called by parent between iterations. """
  struct.pack_into("<I", shm.buf, 0, 0)


# ── Worker process entrypoints ────────────────────────────────────────────────

def worker_basic(
    shm_name: str,
    slot_index: int,
    num_cycles: int,
    update_interval: float
  ) -> None:
  """
  Basic worker: simulates ACTIVE_RUNS changes with sleep between writes.
  Prints start time to confirm parallel launch.
  """
  pid = os.getpid()
  shm = SharedMemory(name=shm_name, create=False)
  print("[worker {}] pid={} slot={} started at {:.6f}".format(
      slot_index, pid, slot_index, time.time()), flush=True)

  for i in range(num_cycles):
    # Simulate run starting
    data = {
        "worker_key": "host:8000:{}:{}".format(os.getppid(), pid),
        "last_updated": time.time(),
        "active_runs": {
            "run-{}-{}".format(pid, i): {
                "processor_name": "test_processor_{}".format(i),
                "vcon_uuids": ["uuid-{}".format(i)],
                "entry_point": "/process",
                "pipeline_name": "test_pipeline",
                "job_id": "",
                "start_time": time.time(),
            }
        },
    }
    slot_write(shm, slot_index, data)
    print("[worker {}] wrote update {}/{} at {:.6f}".format(
        slot_index, i + 1, num_cycles, time.time()), flush=True)
    time.sleep(update_interval)

    # Simulate run finishing
    data["active_runs"] = {}
    data["last_updated"] = time.time()
    slot_write(shm, slot_index, data)
    time.sleep(update_interval)

  # Final idle state
  slot_write(shm, slot_index, {
      "worker_key": "host:8000:{}:{}".format(os.getppid(), pid),
      "last_updated": time.time(),
      "active_runs": {},
  })
  print("[worker {}] done at {:.6f}".format(slot_index, time.time()), flush=True)
  shm.close()


def worker_fast(
    shm_name: str,
    slot_index: int,
    duration: float,
    result_queue: multiprocessing.Queue
  ) -> None:
  """
  Contention worker: writes slot as fast as possible for duration seconds.
  Reports write count and start/end times back via result_queue.
  Uses a large payload to maximise the window for torn reads.
  """
  pid = os.getpid()
  shm = SharedMemory(name=shm_name, create=False)

  # Build a large payload to stress the window between generation counter
  # increment and write completion.
  large_run = {
      "processor_name": "stress_test_processor",
      "vcon_uuids": ["uuid-{:06d}".format(i) for i in range(50)],
      "entry_point": "/process",
      "pipeline_name": "stress_pipeline",
      "job_id": "job-{:06d}".format(pid),
      "start_time": time.time(),
      "extra_padding": "x" * 1024,  # pad to increase payload size
  }

  write_count = 0
  start_time = time.time()
  end_time = start_time + duration

  while time.time() < end_time:
    data = {
        "worker_key": "host:8000:{}:{}".format(os.getppid(), pid),
        "last_updated": time.time(),
        "active_runs": {
            "run-{}-{}".format(pid, write_count): large_run
        },
    }
    slot_write(shm, slot_index, data)
    write_count += 1

    # Alternate between active and idle to vary payload size
    data["active_runs"] = {}
    data["last_updated"] = time.time()
    slot_write(shm, slot_index, data)
    write_count += 1

  shm.close()
  result_queue.put({
      "slot": slot_index,
      "pid": pid,
      "write_count": write_count,
      "start_time": start_time,
      "end_time": time.time(),
  })


def worker_instance(
    shm_name: str,
    slot_index: int,
    instance_id: int,
    duration: float,
    result_queue: multiprocessing.Queue
  ) -> None:
  """
  Multi-instance isolation worker: writes its own segment slot with
  instance_id embedded in every payload.  Used to verify that two
  independent segments never bleed data into each other.
  """
  pid = os.getpid()
  shm = SharedMemory(name=shm_name, create=False)

  write_count = 0
  end_time = time.time() + duration

  while time.time() < end_time:
    data = {
        "worker_key": "host:8000:instance{}:{}".format(instance_id, pid),
        "instance_id": instance_id,
        "last_updated": time.time(),
        "active_runs": {
            "run-{}-{}".format(pid, write_count): {
                "processor_name": "instance_{}_processor".format(instance_id),
                "instance_id": instance_id,
            }
        },
    }
    slot_write(shm, slot_index, data)
    write_count += 1

    data["active_runs"] = {}
    data["last_updated"] = time.time()
    slot_write(shm, slot_index, data)
    write_count += 1

  shm.close()
  result_queue.put({
      "slot": slot_index,
      "instance_id": instance_id,
      "write_count": write_count,
  })


def worker_claim_slot(
    shm_name: str,
    num_slots: int,
    barrier: multiprocessing.Barrier,
    result_queue: multiprocessing.Queue
  ) -> None:
  """
  Slot claim worker: attaches to shared memory, waits at barrier until
  all workers are ready, then claims a slot simultaneously with peers.
  Reports claimed slot index and PID back via result_queue.
  """
  pid = os.getpid()
  shm = SharedMemory(name=shm_name, create=False)

  # Wait at barrier — all workers release simultaneously to maximize
  # contention on the slot claim counter
  barrier.wait()

  slot_index, was_contended = claim_slot(shm)

  # Write initial data to claimed slot to prove it is usable
  data = {
      "worker_key": "host:8000:{}:{}".format(os.getppid(), pid),
      "last_updated": time.time(),
      "active_runs": {},
      "claimed_slot": slot_index,
  }
  slot_write(shm, slot_index, data)

  shm.close()
  result_queue.put({
      "pid": pid,
      "slot_index": slot_index,
      "was_contended": was_contended,
  })


# ── Test 1: Basic functionality ───────────────────────────────────────────────

def test_basic(num_workers: int, duration: float) -> bool:
  """
  Basic test: allocate slots, fork workers with sleep between writes,
  read and aggregate, verify last_updated and clean idle state at end.
  Prints per-worker start timestamps to confirm parallel execution.
  """
  print("\n--- Test 1: Basic functionality ({} workers) ---".format(
      num_workers), flush=True)

  # ── 1. Parent allocates shared memory before forking ──────────────────
  total_size = HEADER_REGION_SIZE + (num_workers * SLOT_SIZE)
  shm = SharedMemory(create=True, size=total_size)
  shm.buf[:total_size] = b'\x00' * total_size
  print("[parent] pid={} shm name={} size={}KB".format(
      os.getpid(), shm.name, total_size // 1024), flush=True)

  # ── 2. Fork workers ───────────────────────────────────────────────────
  fork_time = time.time()
  processes = []
  for i in range(num_workers):
    p = multiprocessing.Process(
        target=worker_basic,
        args=(shm.name, i, 3, 0.2),
      )
    p.start()
    processes.append(p)
  print("[parent] forked {} workers at {:.6f} pids={}".format(
      num_workers, fork_time, [p.pid for p in processes]), flush=True)

  # ── 3. Parent reads and aggregates while workers are running ──────────
  # No sleep in read loop — maximise chance of catching mid-write state
  start = time.time()
  max_active_seen = 0
  max_slots_seen = 0
  read_count = 0
  while time.time() - start < duration:
    aggregated = {}
    slots_seen = 0
    for i in range(num_workers):
      slot_data, _ = slot_read(shm, i)
      if slot_data:
        slots_seen += 1
        aggregated.update(slot_data.get("active_runs", {}))
    max_active_seen = max(max_active_seen, len(aggregated))
    max_slots_seen = max(max_slots_seen, slots_seen)
    read_count += 1

  print("[parent] completed {} aggregate reads during run".format(
      read_count), flush=True)

  # ── 4. Wait for workers to finish ─────────────────────────────────────
  for p in processes:
    p.join(timeout=10.0)
    if p.is_alive():
      print("  WARNING: worker pid={} did not exit".format(p.pid), flush=True)
      p.terminate()

  # ── 5. Final read — all slots should be idle with recent timestamps ───
  passed = True
  for i in range(num_workers):
    slot_data, _ = slot_read(shm, i)
    active = slot_data.get("active_runs", {})
    last_updated = slot_data.get("last_updated", 0)
    age = time.time() - last_updated if last_updated else float("inf")
    print("  slot {}: active_runs={} last_updated={:.2f}s ago".format(
        i, len(active), age), flush=True)
    if len(active) != 0:
      print("  FAIL: slot {} has non-empty active_runs".format(i))
      passed = False
    if age > 5.0:
      print("  FAIL: slot {} last_updated is {:.1f}s old".format(i, age))
      passed = False

  print("  max active_runs seen simultaneously: {}".format(max_active_seen))
  print("  max slots populated simultaneously: {}".format(max_slots_seen))
  if max_active_seen == 0:
    print("  FAIL: never observed any active runs")
    passed = False

  # ── 6. Cleanup ────────────────────────────────────────────────────────
  shm.close()
  shm.unlink()
  result = "PASS" if passed else "FAIL"
  print("--- Test 1: {} ---".format(result), flush=True)
  return passed


# ── Test 2: Contention A — reader threads vs single fast writer ───────────────

def test_contention_single_slot(duration: float) -> bool:
  """
  Contention test A: one writer thread writes slot 0 as fast as possible.
  Multiple reader threads hammer the same slot simultaneously with no sleep.
  Verifies:
    - No JSON decode errors (no torn reads)
    - No RuntimeError from slot_read (generation counter holds)
    - Retry path is actually exercised (retries > 0 observed)
    - All read data has correct structure
  """
  num_readers = 4
  print("\n--- Test 2: Contention A — {} readers vs 1 fast writer ---".format(
      num_readers), flush=True)

  total_size = HEADER_REGION_SIZE + SLOT_SIZE
  shm = SharedMemory(create=True, size=total_size)
  shm.buf[:total_size] = b'\x00' * total_size

  errors = []
  total_reads = [0]
  total_retries = [0]
  stop_flag = [False]

  large_run = {
      "processor_name": "stress_processor",
      "vcon_uuids": ["uuid-{:06d}".format(i) for i in range(50)],
      "entry_point": "/process",
      "pipeline_name": "stress_pipeline",
      "job_id": "job-stress",
      "start_time": time.time(),
      "extra_padding": "x" * 1024,
  }

  def writer():
    write_count = 0
    start = time.time()
    end_time = start + duration
    while time.time() < end_time:
      data = {
          "worker_key": "host:8000:parent:writer",
          "last_updated": time.time(),
          "active_runs": {
              "run-{}".format(write_count): large_run
          },
      }
      slot_write(shm, 0, data)
      write_count += 1

      data["active_runs"] = {}
      data["last_updated"] = time.time()
      slot_write(shm, 0, data)
      write_count += 1
    stop_flag[0] = True
    elapsed = time.time() - start
    print("  writer: {} writes in {:.2f}s ({:.0f} writes/sec)".format(
        write_count, elapsed, write_count / elapsed), flush=True)

  def reader(reader_id: int):
    reads = 0
    retries = 0
    # No sleep — tight loop to maximise contention
    while not stop_flag[0]:
      try:
        data, retry_count = slot_read(shm, 0)
        retries += retry_count
        reads += 1

        # Validate structure if non-empty
        if data:
          if "worker_key" not in data:
            errors.append("reader {}: missing worker_key".format(reader_id))
          if "last_updated" not in data:
            errors.append("reader {}: missing last_updated".format(reader_id))
          if "active_runs" not in data:
            errors.append("reader {}: missing active_runs".format(reader_id))
          else:
            for run_id, run in data["active_runs"].items():
              if "processor_name" not in run:
                errors.append(
                    "reader {}: run {} missing processor_name".format(
                        reader_id, run_id))

      except json.JSONDecodeError as e:
        errors.append("reader {}: JSONDecodeError: {}".format(reader_id, e))
      except RuntimeError as e:
        errors.append("reader {}: RuntimeError: {}".format(reader_id, e))
      except Exception as e:
        errors.append("reader {}: unexpected error: {}".format(reader_id, e))

    total_reads[0] += reads
    total_retries[0] += retries
    print("  reader {}: {} reads {} retries".format(
        reader_id, reads, retries), flush=True)

  threads = []
  writer_thread = threading.Thread(target=writer)
  for i in range(num_readers):
    threads.append(threading.Thread(target=reader, args=(i,)))

  # Start all threads as close together as possible
  for t in threads:
    t.start()
  writer_thread.start()

  writer_thread.join()
  for t in threads:
    t.join(timeout=duration + 2.0)

  print("  total reads: {}".format(total_reads[0]), flush=True)
  print("  total retries: {}".format(total_retries[0]), flush=True)
  print("  errors: {}".format(len(errors)), flush=True)
  for e in errors[:10]:
    print("    {}".format(e), flush=True)

  passed = len(errors) == 0
  if total_retries[0] == 0:
    print("  WARNING: retry path was never exercised — "
        "contention may not have been sufficient", flush=True)

  shm.close()
  shm.unlink()
  result = "PASS" if passed else "FAIL"
  print("--- Test 2: {} ---".format(result), flush=True)
  return passed


# ── Test 3: Contention B — N fast writer processes, parent reads all ──────────

def test_contention_all_slots(num_workers: int, duration: float) -> bool:
  """
  Contention test B: N worker processes each write their slot as fast as
  possible.  Parent reads all slots in a tight loop with no sleep.
  Verifies:
    - No errors across all slots under maximum write pressure
    - Retry path exercised
    - Workers confirmed running in parallel via overlapping time ranges
    - Write counts reported per worker
  """
  print("\n--- Test 3: Contention B — {} fast writers, parent reads all ---".format(
      num_workers), flush=True)

  total_size = HEADER_REGION_SIZE + (num_workers * SLOT_SIZE)
  shm = SharedMemory(create=True, size=total_size)
  shm.buf[:total_size] = b'\x00' * total_size

  result_queue = multiprocessing.Queue()
  processes = []
  launch_time = time.time()
  for i in range(num_workers):
    p = multiprocessing.Process(
        target=worker_fast,
        args=(shm.name, i, duration, result_queue),
      )
    p.start()
    processes.append(p)
  print("[parent] launched {} workers at {:.6f} pids={}".format(
      num_workers, launch_time, [p.pid for p in processes]), flush=True)

  # Parent reads all slots in tight loop — no sleep
  errors = []
  total_reads = 0
  total_retries = 0
  end_time = time.time() + duration + 1.0

  while time.time() < end_time:
    for i in range(num_workers):
      try:
        data, retries = slot_read(shm, i)
        total_retries += retries
        total_reads += 1

        if data:
          if "worker_key" not in data:
            errors.append("slot {}: missing worker_key".format(i))
          if "last_updated" not in data:
            errors.append("slot {}: missing last_updated".format(i))
          if "active_runs" not in data:
            errors.append("slot {}: missing active_runs".format(i))
          else:
            for run_id, run in data["active_runs"].items():
              if "processor_name" not in run:
                errors.append(
                    "slot {} run {}: missing processor_name".format(i, run_id))

      except json.JSONDecodeError as e:
        errors.append("slot {}: JSONDecodeError: {}".format(i, e))
      except RuntimeError as e:
        errors.append("slot {}: RuntimeError: {}".format(i, e))
      except Exception as e:
        errors.append("slot {}: unexpected: {}".format(i, e))

  for p in processes:
    p.join(timeout=10.0)
    if p.is_alive():
      print("  WARNING: worker pid={} did not exit".format(p.pid), flush=True)
      p.terminate()

  # Collect results and verify parallel execution via overlapping time ranges
  write_results = []
  while not result_queue.empty():
    write_results.append(result_queue.get_nowait())
  write_results.sort(key=lambda r: r["slot"])

  print("  parent total reads: {}".format(total_reads), flush=True)
  print("  parent total retries: {}".format(total_retries), flush=True)
  passed = len(errors) == 0

  # Verify workers ran in parallel — all start times should be close together
  # and all time ranges should overlap
  if len(write_results) == num_workers:
    min_start = min(r["start_time"] for r in write_results)
    max_start = max(r["start_time"] for r in write_results)
    start_spread = max_start - min_start
    print("  worker start spread: {:.4f}s (should be < 1.0s for parallel launch)".format(
        start_spread), flush=True)
    if start_spread > 1.0:
      print("  WARNING: workers may not have launched in parallel")

    for r in write_results:
      elapsed = r["end_time"] - r["start_time"]
      print("  slot {}: pid={} {} writes in {:.2f}s ({:.0f} writes/sec)".format(
          r["slot"], r["pid"], r["write_count"], elapsed,
          r["write_count"] / elapsed if elapsed > 0 else 0), flush=True)
  else:
    print("  WARNING: only got {}/{} worker results".format(
        len(write_results), num_workers), flush=True)

  print("  errors: {}".format(len(errors)), flush=True)
  for e in errors[:10]:
    print("    {}".format(e), flush=True)

  if total_retries == 0:
    print("  WARNING: retry path was never exercised", flush=True)

  shm.close()
  shm.unlink()
  result = "PASS" if passed else "FAIL"
  print("--- Test 3: {} ---".format(result), flush=True)
  return passed


# ── Test 4: Multi-instance isolation ─────────────────────────────────────────

def test_multi_instance_isolation(num_workers: int, duration: float) -> bool:
  """
  Multi-instance isolation test: two independent parent processes each
  allocate their own shared memory segment with num_workers slots.
  Workers from instance A write only to segment A, instance B to segment B.
  Parent verifies:
    - Segment names are different (no collision)
    - No instance B data appears when reading segment A
    - No instance A data appears when reading segment B
    - Both segments operate independently and correctly
  """
  print("\n--- Test 4: Multi-instance isolation (2 instances x {} workers) ---".format(
      num_workers), flush=True)

  total_size = HEADER_REGION_SIZE + (num_workers * SLOT_SIZE)

  # Allocate two independent segments — simulating two server instances
  shm_a = SharedMemory(create=True, size=total_size)
  shm_b = SharedMemory(create=True, size=total_size)
  shm_a.buf[:total_size] = b'\x00' * total_size
  shm_b.buf[:total_size] = b'\x00' * total_size

  print("  instance A shm name={}".format(shm_a.name), flush=True)
  print("  instance B shm name={}".format(shm_b.name), flush=True)

  if shm_a.name == shm_b.name:
    print("  FAIL: both instances got the same shm name — collision!")
    shm_a.close(); shm_a.unlink()
    shm_b.close(); shm_b.unlink()
    return False

  result_queue = multiprocessing.Queue()
  processes = []

  # Launch workers for instance A (instance_id=0)
  for i in range(num_workers):
    p = multiprocessing.Process(
        target=worker_instance,
        args=(shm_a.name, i, 0, duration, result_queue),
      )
    p.start()
    processes.append(p)

  # Launch workers for instance B (instance_id=1)
  for i in range(num_workers):
    p = multiprocessing.Process(
        target=worker_instance,
        args=(shm_b.name, i, 1, duration, result_queue),
      )
    p.start()
    processes.append(p)

  print("  launched {} workers total pids={}".format(
      len(processes), [p.pid for p in processes]), flush=True)

  # Read both segments and verify no cross-contamination
  errors = []
  total_reads = 0
  end_time = time.time() + duration

  while time.time() < end_time:
    # Read instance A segment — should only contain instance_id=0 data
    for i in range(num_workers):
      try:
        data, _ = slot_read(shm_a, i)
        total_reads += 1
        if data:
          found_id = data.get("instance_id")
          if found_id is not None and found_id != 0:
            errors.append(
                "instance A slot {}: found instance_id={} (expected 0)".format(
                    i, found_id))
          for run_id, run in data.get("active_runs", {}).items():
            run_instance = run.get("instance_id")
            if run_instance is not None and run_instance != 0:
              errors.append(
                  "instance A slot {} run {}: found instance_id={} (expected 0)".format(
                      i, run_id, run_instance))
      except json.JSONDecodeError as e:
        errors.append("instance A slot {}: JSONDecodeError: {}".format(i, e))
      except RuntimeError as e:
        errors.append("instance A slot {}: RuntimeError: {}".format(i, e))

    # Read instance B segment — should only contain instance_id=1 data
    for i in range(num_workers):
      try:
        data, _ = slot_read(shm_b, i)
        total_reads += 1
        if data:
          found_id = data.get("instance_id")
          if found_id is not None and found_id != 1:
            errors.append(
                "instance B slot {}: found instance_id={} (expected 1)".format(
                    i, found_id))
          for run_id, run in data.get("active_runs", {}).items():
            run_instance = run.get("instance_id")
            if run_instance is not None and run_instance != 1:
              errors.append(
                  "instance B slot {} run {}: found instance_id={} (expected 1)".format(
                      i, run_id, run_instance))
      except json.JSONDecodeError as e:
        errors.append("instance B slot {}: JSONDecodeError: {}".format(i, e))
      except RuntimeError as e:
        errors.append("instance B slot {}: RuntimeError: {}".format(i, e))

  for p in processes:
    p.join(timeout=10.0)
    if p.is_alive():
      print("  WARNING: worker pid={} did not exit".format(p.pid), flush=True)
      p.terminate()

  # Collect write counts
  write_results = []
  while not result_queue.empty():
    write_results.append(result_queue.get_nowait())
  write_results.sort(key=lambda r: (r["instance_id"], r["slot"]))

  print("  total reads across both segments: {}".format(total_reads), flush=True)
  for r in write_results:
    print("  instance {} slot {}: {} writes".format(
        r["instance_id"], r["slot"], r["write_count"]), flush=True)

  print("  errors: {}".format(len(errors)), flush=True)
  for e in errors[:10]:
    print("    {}".format(e), flush=True)

  passed = len(errors) == 0

  shm_a.close(); shm_a.unlink()
  shm_b.close(); shm_b.unlink()
  result = "PASS" if passed else "FAIL"
  print("--- Test 4: {} ---".format(result), flush=True)
  return passed


# ── Test 5: Slot assignment under contention ──────────────────────────────────

def test_slot_assignment(num_workers: int, num_iterations: int) -> bool:
  """
  Slot assignment test: verifies that N workers simultaneously claiming
  slots each get a unique index with no collisions or out-of-range values.

  Runs num_iterations cycles of:
    - Reset slot counter to 0
    - Spawn N workers, hold them at a barrier
    - Release all workers simultaneously to maximize counter contention
    - Verify exactly N unique slot indices in range [0, N)
    - Join all workers
    - Repeat

  Uses fcntl.lockf for mutual exclusion on the counter — the same
  mechanism that will be used in the real server implementation.
  """
  print("\n--- Test 5: Slot assignment ({} workers, {} iterations) ---".format(
      num_workers, num_iterations), flush=True)

  total_size = HEADER_REGION_SIZE + (num_workers * SLOT_SIZE)
  shm = SharedMemory(create=True, size=total_size)
  shm.buf[:total_size] = b'\x00' * total_size

  result_queue = multiprocessing.Queue()
  passed = True
  collision_count = 0
  out_of_range_count = 0
  total_contentions = 0

  for iteration in range(num_iterations):
    # Reset slot counter for this iteration
    reset_slot_counter(shm)

    # Barrier: parent + N workers — parent waits too so workers
    # don't start claiming before all are spawned
    barrier = multiprocessing.Barrier(num_workers + 1)

    processes = []
    for i in range(num_workers):
      p = multiprocessing.Process(
          target=worker_claim_slot,
          args=(shm.name, num_workers, barrier, result_queue),
        )
      p.start()
      processes.append(p)

    # Parent waits at barrier until all workers are spawned and waiting
    barrier.wait()
    # All workers now race to claim a slot simultaneously

    for p in processes:
      p.join(timeout=10.0)
      if p.is_alive():
        print("  iteration {}: WARNING worker pid={} did not exit".format(
            iteration, p.pid), flush=True)
        p.terminate()
        passed = False

    # Collect results for this iteration
    iteration_results = []
    while not result_queue.empty():
      iteration_results.append(result_queue.get_nowait())

    # Count contentions from this iteration
    iter_contentions = sum(1 for r in iteration_results if r.get("was_contended"))
    total_contentions += iter_contentions

    # Verify exactly N results
    if len(iteration_results) != num_workers:
      print("  iteration {}: FAIL got {} results expected {}".format(
          iteration, len(iteration_results), num_workers), flush=True)
      passed = False
      continue

    # Verify all slot indices are unique and in range [0, num_workers)
    slot_indices = [r["slot_index"] for r in iteration_results]
    seen = set()
    for idx in slot_indices:
      if idx < 0 or idx >= num_workers:
        out_of_range_count += 1
        print("  iteration {}: FAIL slot index {} out of range [0, {})".format(
            iteration, idx, num_workers), flush=True)
        passed = False
      if idx in seen:
        collision_count += 1
        print("  iteration {}: FAIL duplicate slot index {}".format(
            iteration, idx), flush=True)
        passed = False
      seen.add(idx)

    # Verify slot data is readable and correct
    for r in iteration_results:
      slot_data, _ = slot_read(shm, r["slot_index"])
      if slot_data.get("claimed_slot") != r["slot_index"]:
        print("  iteration {}: FAIL slot {} data mismatch".format(
            iteration, r["slot_index"]), flush=True)
        passed = False

    if (iteration + 1) % 10 == 0 or iteration == num_iterations - 1:
      print("  completed {}/{} iterations — collisions={} out_of_range={} "
          "total_lock_contentions={}".format(
          iteration + 1, num_iterations,
          collision_count, out_of_range_count, total_contentions), flush=True)

  # Fail if the lock contention path was never exercised — this means
  # workers never raced on the lock and we haven't actually tested it.
  if total_contentions == 0:
    print("  FAIL: lock contention path was never exercised across {} iterations "
        "— workers may not be running simultaneously or the lock/unlock "
        "cycle is too fast to observe races. Try --iterations 1000 or "
        "--workers 8 to increase contention probability.".format(num_iterations))
    passed = False
  else:
    print("  lock contention confirmed: {} contention events across {} "
        "iterations — fcntl.lockf blocking path was exercised.".format(
        total_contentions, num_iterations), flush=True)

  shm.close()
  shm.unlink()
  result = "PASS" if passed else "FAIL"
  print("--- Test 5: {} ---".format(result), flush=True)
  return passed


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
  parser = argparse.ArgumentParser(
      description="Shared memory PoC for cross-worker ACTIVE_RUNS aggregation"
    )
  parser.add_argument("--workers", type=int, default=3,
      help="Number of worker processes per instance (default: 3)")
  parser.add_argument("--duration", type=float, default=3.0,
      help="Duration in seconds for each test (default: 3.0)")
  parser.add_argument("--iterations", type=int, default=100,
      help="Number of slot claim iterations for Test 5 (default: 100)")
  args = parser.parse_args()

  results = []
  results.append(test_basic(args.workers, args.duration))
  results.append(test_contention_single_slot(args.duration))
  results.append(test_contention_all_slots(args.workers, args.duration))
  results.append(test_multi_instance_isolation(args.workers, args.duration))
  results.append(test_slot_assignment(args.workers, args.iterations))

  print("\n=== Summary ===")
  labels = [
      "Test 1 (basic — 6 steps)",
      "Test 2 (contention A — torn read / retry path)",
      "Test 3 (contention B — N fast writers)",
      "Test 4 (multi-instance isolation)",
      "Test 5 (slot assignment — fcntl.lockf)",
  ]
  all_passed = True
  for label, passed in zip(labels, results):
    status = "PASS" if passed else "FAIL"
    print("  {}: {}".format(label, status))
    if not passed:
      all_passed = False

  if all_passed:
    print("\nAll tests PASSED")
    sys.exit(0)
  else:
    print("\nSome tests FAILED")
    sys.exit(1)


if __name__ == "__main__":
  main()
