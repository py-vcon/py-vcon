# Copyright (C) 2023-2026 SIPez LLC.  All rights reserved.
"""
Unit tests for processor timeout feature.

Tests the timeout parameter on /process/{uuid}/{processor} and
/processIO/{processor} endpoints.

Test processors are loaded via PLUGIN_PATHS mechanism (set in conftest.py),
which causes py_vcon_server to create REST API routes for them.
"""
import os
import time
import importlib
import pytest
import pytest_asyncio
import fastapi.testclient
import vcon
import py_vcon_server
import py_vcon_server.processor
import py_vcon_server.db
import py_vcon_server.settings
from py_vcon_server.settings import VCON_STORAGE_URL


# ============================================================
#  Test Fixtures
# ============================================================

UUID = "01936677-0000-8000-8000-111111111111"


def make_test_vcon() -> vcon.Vcon:
    """Create a minimal test vCon."""
    v = vcon.Vcon()
    v._vcon_dict["uuid"] = UUID
    v.set_party_parameter("tel", "+15551234567")
    v.set_party_parameter("name", "Test User", 0)
    v.set_subject("Test conversation for timeout testing")
    v.add_dialog_inline_text(
        "Hello, this is a test message.",
        "2024-03-06T20:07:43+00:00",
        5.0,
        0,
        vcon.Vcon.MEDIATYPE_TEXT_PLAIN
    )
    return v


VCON_STORAGE = None


@pytest_asyncio.fixture(autouse=True)
async def setup_storage():
    """Setup and teardown VconStorage for each test."""
    vs = py_vcon_server.db.VconStorage.instantiate(VCON_STORAGE_URL)
    global VCON_STORAGE
    VCON_STORAGE = vs
    yield
    VCON_STORAGE = None
    await vs.shutdown()


# ============================================================
#  Verify processors are loaded
# ============================================================

def test_timeout_processors_registered():
    """Verify that timeout test processors are registered."""
    names = py_vcon_server.processor.VconProcessorRegistry.get_processor_names()
    assert "timeout_test_sleep_async" in names, "timeout_test_sleep_async not registered"
    assert "timeout_test_sleep_sync" in names, "timeout_test_sleep_sync not registered"
    assert "timeout_test_success" in names, "timeout_test_success not registered"
    assert "timeout_test_exception" in names, "timeout_test_exception not registered"


# ============================================================
#  Tests: /process/{uuid}/{processor} endpoint
# ============================================================

@pytest.mark.asyncio
async def test_process_async_timeout_fires():
    """Test that async processor times out when sleep exceeds timeout."""
    in_vcon = make_test_vcon()
    
    with fastapi.testclient.TestClient(py_vcon_server.restapi) as client:
        # Store the vCon
        set_response = client.post("/vcon", json=in_vcon.dumpd())
        assert set_response.status_code == 204
        
        # Run processor with short timeout, long sleep
        start_time = time.time()
        post_response = client.post(
            "/process/{}/timeout_test_sleep_async".format(UUID),
            params={"timeout": 1.0},
            json={"sleep_seconds": 5.0}
        )
        elapsed = time.time() - start_time
        
        # Should timeout with 430 status
        assert post_response.status_code == 430, f"Expected 430, got {post_response.status_code}: {post_response.json()}"
        assert "timed out" in post_response.json()["detail"]
        assert "timeout_test_sleep_async" in post_response.json()["detail"]
        
        # Should have taken approximately the timeout duration, not the sleep duration
        assert elapsed < 3.0, "Timeout should have fired before sleep completed"
        
        # Cleanup
        client.delete("/vcon/{}".format(UUID))


@pytest.mark.asyncio
async def test_process_async_completes_in_time():
    """Test that async processor completes when sleep is less than timeout."""
    in_vcon = make_test_vcon()
    
    with fastapi.testclient.TestClient(py_vcon_server.restapi) as client:
        # Store the vCon
        set_response = client.post("/vcon", json=in_vcon.dumpd())
        assert set_response.status_code == 204
        
        # Run processor with long timeout, short sleep
        start_time = time.time()
        post_response = client.post(
            "/process/{}/timeout_test_sleep_async".format(UUID),
            params={"timeout": 10.0},
            json={"sleep_seconds": 1.0}
        )
        elapsed = time.time() - start_time
        
        # Should succeed with 200 status
        assert post_response.status_code == 200
        
        # Should have taken approximately the sleep duration
        assert elapsed < 3.0, "Should have completed quickly"
        
        # Cleanup
        client.delete("/vcon/{}".format(UUID))


@pytest.mark.asyncio
async def test_process_sync_blocks_timeout():
    """Test that sync processor blocks timeout from firing."""
    in_vcon = make_test_vcon()
    
    with fastapi.testclient.TestClient(py_vcon_server.restapi) as client:
        # Store the vCon
        set_response = client.post("/vcon", json=in_vcon.dumpd())
        assert set_response.status_code == 204
        
        # Run processor with short timeout, longer sync sleep
        start_time = time.time()
        post_response = client.post(
            "/process/{}/timeout_test_sleep_sync".format(UUID),
            params={"timeout": 1.0},
            json={"sleep_seconds": 3.0}
        )
        elapsed = time.time() - start_time
        
        # Should succeed (timeout couldn't interrupt sync sleep)
        assert post_response.status_code == 200
        
        # Should have taken approximately the sleep duration (timeout didn't help)
        assert elapsed >= 2.5, "Sync sleep should have blocked the full duration"
        
        # Cleanup
        client.delete("/vcon/{}".format(UUID))


@pytest.mark.asyncio
async def test_process_zero_timeout_disables():
    """Test that timeout=0 disables timeout."""
    in_vcon = make_test_vcon()
    
    with fastapi.testclient.TestClient(py_vcon_server.restapi) as client:
        # Store the vCon
        set_response = client.post("/vcon", json=in_vcon.dumpd())
        assert set_response.status_code == 204
        
        # Run processor with timeout=0 (disabled), short sleep
        post_response = client.post(
            "/process/{}/timeout_test_sleep_async".format(UUID),
            params={"timeout": 0},
            json={"sleep_seconds": 1.0}
        )
        
        # Should succeed
        assert post_response.status_code == 200
        
        # Cleanup
        client.delete("/vcon/{}".format(UUID))


@pytest.mark.asyncio
async def test_process_success_with_default_timeout():
    """Test that immediate success works with default timeout."""
    in_vcon = make_test_vcon()
    
    with fastapi.testclient.TestClient(py_vcon_server.restapi) as client:
        # Store the vCon
        set_response = client.post("/vcon", json=in_vcon.dumpd())
        assert set_response.status_code == 204
        
        # Run processor without specifying timeout (uses default)
        post_response = client.post(
            "/process/{}/timeout_test_success".format(UUID),
            json={}
        )
        
        # Should succeed
        assert post_response.status_code == 200
        
        # Cleanup
        client.delete("/vcon/{}".format(UUID))


@pytest.mark.asyncio
async def test_process_exception_propagates():
    """Test that exceptions propagate correctly, not masked by timeout."""
    in_vcon = make_test_vcon()
    
    with fastapi.testclient.TestClient(py_vcon_server.restapi) as client:
        # Store the vCon
        set_response = client.post("/vcon", json=in_vcon.dumpd())
        assert set_response.status_code == 204
        
        # Run processor that raises exception
        post_response = client.post(
            "/process/{}/timeout_test_exception".format(UUID),
            json={"message": "Custom error message"}
        )
        
        # Should return 500 with exception info
        assert post_response.status_code == 500
        assert "Custom error message" in post_response.json()["exception"]
        
        # Cleanup
        client.delete("/vcon/{}".format(UUID))


# ============================================================
#  Tests: /processIO/{processor} endpoint
# ============================================================

@pytest.mark.asyncio
async def test_processio_async_timeout_fires():
    """Test that async processor times out via /processIO endpoint."""
    in_vcon = make_test_vcon()
    
    with fastapi.testclient.TestClient(py_vcon_server.restapi) as client:
        request_body = {
            "processor_io": {
                "vcons": [in_vcon.dumpd()],
                "parameters": {}
            },
            "processor_options": {
                "sleep_seconds": 5.0
            }
        }
        
        start_time = time.time()
        post_response = client.post(
            "/processIO/timeout_test_sleep_async",
            params={"timeout": 1.0},
            json=request_body
        )
        elapsed = time.time() - start_time
        
        # Should timeout with 430 status
        assert post_response.status_code == 430, f"Expected 430, got {post_response.status_code}: {post_response.json()}"
        assert "timed out" in post_response.json()["detail"]
        
        # Should have taken approximately the timeout duration
        assert elapsed < 3.0, "Timeout should have fired before sleep completed"


@pytest.mark.asyncio
async def test_processio_async_completes_in_time():
    """Test that async processor completes via /processIO endpoint."""
    in_vcon = make_test_vcon()
    
    with fastapi.testclient.TestClient(py_vcon_server.restapi) as client:
        request_body = {
            "processor_io": {
                "vcons": [in_vcon.dumpd()],
                "parameters": {}
            },
            "processor_options": {
                "sleep_seconds": 1.0
            }
        }
        
        post_response = client.post(
            "/processIO/timeout_test_sleep_async",
            params={"timeout": 10.0},
            json=request_body
        )
        
        # Should succeed
        assert post_response.status_code == 200


@pytest.mark.asyncio
async def test_processio_sync_blocks_timeout():
    """Test that sync processor blocks timeout via /processIO endpoint."""
    in_vcon = make_test_vcon()
    
    with fastapi.testclient.TestClient(py_vcon_server.restapi) as client:
        request_body = {
            "processor_io": {
                "vcons": [in_vcon.dumpd()],
                "parameters": {}
            },
            "processor_options": {
                "sleep_seconds": 3.0
            }
        }
        
        start_time = time.time()
        post_response = client.post(
            "/processIO/timeout_test_sleep_sync",
            params={"timeout": 1.0},
            json=request_body
        )
        elapsed = time.time() - start_time
        
        # Should succeed (timeout couldn't interrupt)
        assert post_response.status_code == 200
        
        # Should have taken full sleep duration
        assert elapsed >= 2.5, "Sync sleep should have blocked"


@pytest.mark.asyncio
async def test_processio_zero_timeout_disables():
    """Test that timeout=0 disables timeout via /processIO endpoint."""
    in_vcon = make_test_vcon()
    
    with fastapi.testclient.TestClient(py_vcon_server.restapi) as client:
        request_body = {
            "processor_io": {
                "vcons": [in_vcon.dumpd()],
                "parameters": {}
            },
            "processor_options": {
                "sleep_seconds": 1.0
            }
        }
        
        post_response = client.post(
            "/processIO/timeout_test_sleep_async",
            params={"timeout": 0},
            json=request_body
        )
        
        # Should succeed
        assert post_response.status_code == 200


@pytest.mark.asyncio
async def test_processio_exception_propagates():
    """Test that exceptions propagate via /processIO endpoint."""
    in_vcon = make_test_vcon()
    
    with fastapi.testclient.TestClient(py_vcon_server.restapi) as client:
        request_body = {
            "processor_io": {
                "vcons": [in_vcon.dumpd()],
                "parameters": {}
            },
            "processor_options": {
                "message": "ProcessIO error message"
            }
        }
        
        post_response = client.post(
            "/processIO/timeout_test_exception",
            json=request_body
        )
        
        # Should return 500 with exception info
        assert post_response.status_code == 500
        assert "ProcessIO error message" in post_response.json()["exception"]


# ============================================================
#  Tests: Default timeout from settings
# ============================================================

@pytest.mark.asyncio
async def test_default_timeout_from_settings():
    """Test that default timeout comes from settings when not specified."""
    in_vcon = make_test_vcon()
    
    # Save original settings that get re-parsed on reload
    original_timeout_env = os.environ.get("DEFAULT_PROCESSOR_TIMEOUT", None)
    original_work_queues_env = os.environ.get("WORK_QUEUES", None)
    
    try:
        # Clear WORK_QUEUES to avoid parsing issues on reload
        if "WORK_QUEUES" in os.environ:
            del os.environ["WORK_QUEUES"]
        
        # Set a short default timeout via env var
        os.environ["DEFAULT_PROCESSOR_TIMEOUT"] = "2"
        importlib.reload(py_vcon_server.settings)
        
        # Reload py_vcon_server to pick up new default in endpoint signature
        importlib.reload(py_vcon_server)
        
        with fastapi.testclient.TestClient(py_vcon_server.restapi) as client:
            # Store the vCon
            set_response = client.post("/vcon", json=in_vcon.dumpd())
            assert set_response.status_code == 204
            
            # Run processor WITHOUT specifying timeout (should use default of 2s)
            start_time = time.time()
            post_response = client.post(
                "/process/{}/timeout_test_sleep_async".format(UUID),
                json={"sleep_seconds": 5.0}
            )
            elapsed = time.time() - start_time
            
            # Should timeout with 430 status
            assert post_response.status_code == 430
            
            # Should have timed out around 2 seconds (the default)
            assert elapsed < 4.0, "Should have timed out using default"
            
            # Cleanup
            client.delete("/vcon/{}".format(UUID))
    
    finally:
        # Restore original settings
        if original_timeout_env is None:
            os.environ.pop("DEFAULT_PROCESSOR_TIMEOUT", None)
        else:
            os.environ["DEFAULT_PROCESSOR_TIMEOUT"] = original_timeout_env
        
        if original_work_queues_env is None:
            os.environ.pop("WORK_QUEUES", None)
        else:
            os.environ["WORK_QUEUES"] = original_work_queues_env
        
        importlib.reload(py_vcon_server.settings)
        importlib.reload(py_vcon_server)


@pytest.mark.asyncio
async def test_param_overrides_default_timeout():
    """Test that timeout parameter overrides default setting."""
    in_vcon = make_test_vcon()
    
    # Save original settings that get re-parsed on reload
    original_timeout_env = os.environ.get("DEFAULT_PROCESSOR_TIMEOUT", None)
    original_work_queues_env = os.environ.get("WORK_QUEUES", None)
    
    try:
        # Clear WORK_QUEUES to avoid parsing issues on reload
        if "WORK_QUEUES" in os.environ:
            del os.environ["WORK_QUEUES"]
        
        # Set a long default timeout via env var
        os.environ["DEFAULT_PROCESSOR_TIMEOUT"] = "10"
        importlib.reload(py_vcon_server.settings)
        importlib.reload(py_vcon_server)
        
        with fastapi.testclient.TestClient(py_vcon_server.restapi) as client:
            # Store the vCon
            set_response = client.post("/vcon", json=in_vcon.dumpd())
            assert set_response.status_code == 204
            
            # Run processor WITH explicit short timeout (should override default)
            start_time = time.time()
            post_response = client.post(
                "/process/{}/timeout_test_sleep_async".format(UUID),
                params={"timeout": 1.0},
                json={"sleep_seconds": 5.0}
            )
            elapsed = time.time() - start_time
            
            # Should timeout with 430 status
            assert post_response.status_code == 430
            
            # Should have timed out around 1 second (the override), not 10 (the default)
            assert elapsed < 3.0, "Should have used override timeout, not default"
            
            # Cleanup
            client.delete("/vcon/{}".format(UUID))
    
    finally:
        # Restore original settings
        if original_timeout_env is None:
            os.environ.pop("DEFAULT_PROCESSOR_TIMEOUT", None)
        else:
            os.environ["DEFAULT_PROCESSOR_TIMEOUT"] = original_timeout_env
        
        if original_work_queues_env is None:
            os.environ.pop("WORK_QUEUES", None)
        else:
            os.environ["WORK_QUEUES"] = original_work_queues_env
        
        importlib.reload(py_vcon_server.settings)
        importlib.reload(py_vcon_server)


# ============================================================
#  Tests: Edge cases
# ============================================================

@pytest.mark.asyncio
async def test_vcon_not_found_returns_404_not_timeout():
    """Test that vCon not found returns 404, not timeout error."""
    
    with fastapi.testclient.TestClient(py_vcon_server.restapi) as client:
        # Try to process non-existent vCon
        post_response = client.post(
            "/process/{}/timeout_test_success".format("nonexistent-uuid-12345"),
            params={"timeout": 1.0},
            json={}
        )
        
        # Should return 404, not 430
        assert post_response.status_code == 404
        assert "not found" in post_response.json()["detail"].lower()
