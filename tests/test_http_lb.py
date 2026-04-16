# Copyright (C) 2023-2026 SIPez LLC.  All rights reserved.
"""
Unit tests for vcon.http_lb – HTTP load balancing and failover utilities.
"""

import asyncio
import typing

import urllib.parse
import httpx
import pytest
import pytest_httpserver

import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
from vcon.http_lb import ParsedMultiHostUrl, HttpLb, ResolvedAddress


# ===================================================================
# ParsedMultiHostUrl
# ===================================================================

class TestIsMultiHost:
    def test_single_host(self):
        assert HttpLb.is_multi_host_url(
            "http://localhost:8000/vcon") is False

    def test_multi_host(self):
        assert HttpLb.is_multi_host_url(
            "http://host1:8000,host2:8001/vcon") is True

    def test_multi_host_with_auth(self):
        assert HttpLb.is_multi_host_url(
            "http://:secret@host1:8000,host2:8001/path") is True

    def test_template_url(self):
        assert HttpLb.is_multi_host_url(
            "http://{host}:{port}/vcon") is False

    def test_single_host_no_port(self):
        assert HttpLb.is_multi_host_url(
            "http://example.com/path") is False


class TestParse:
    def test_single_host_with_port(self):
        r = HttpLb.parse_url("http://localhost:8000/vcon")
        assert r.scheme == "http"
        assert r.password is None
        assert r.host_ports == [("localhost", 8000)]
        assert r.path == "/vcon"

    def test_multi_host(self):
        r = HttpLb.parse_url("http://host1:8000,host2:8001/vcon")
        assert r.scheme == "http"
        assert r.password is None
        assert len(r.host_ports) == 2
        assert ("host1", 8000) in r.host_ports
        assert ("host2", 8001) in r.host_ports
        assert r.path == "/vcon"

    def test_multi_host_with_password(self):
        r = HttpLb.parse_url(
            "http://:mysecret@host1:6379,host2:6380/master_name?db=0"
        )
        assert r.scheme == "http"
        assert r.password == "mysecret"
        assert r.host_ports == [("host1", 6379), ("host2", 6380)]
        assert r.path == "/master_name?db=0"

    def test_https(self):
        r = HttpLb.parse_url("https://secure.example.com/api")
        assert r.scheme == "https"
        assert r.host_ports == [("secure.example.com", 443)]

    def test_three_hosts(self):
        r = HttpLb.parse_url("http://a:1,b:2,c:3/path")
        assert len(r.host_ports) == 3

    def test_ipv6_host(self):
        r = HttpLb.parse_url("http://[::1]:8000/vcon")
        assert r.host_ports == [("::1", 8000)]

    def test_mixed_ipv4_dns(self):
        r = HttpLb.parse_url(
            "http://192.168.1.1:8000,myhost.example.com:8001/vcon"
        )
        assert r.host_ports == [
            ("192.168.1.1", 8000),
            ("myhost.example.com", 8001),
        ]

    def test_no_path_gets_slash(self):
        r = HttpLb.parse_url("http://host:8000")
        assert r.path == "/"

    def test_invalid_url_raises(self):
        with pytest.raises(ValueError):
            HttpLb.parse_url("not_a_url")

    def test_default_port_http(self):
        r = HttpLb.parse_url("http://example.com/path")
        assert r.host_ports == [("example.com", 80)]

    def test_default_port_https(self):
        r = HttpLb.parse_url("https://example.com/path")
        assert r.host_ports == [("example.com", 443)]

    def test_mixed_ports_some_missing(self):
        """host1 has no port (defaults to 80), host2 has explicit port."""
        r = HttpLb.parse_url("http://host1,host2:9000/path")
        assert r.host_ports == [("host1", 80), ("host2", 9000)]

    def test_all_hosts_no_ports(self):
        r = HttpLb.parse_url("https://a,b,c/path")
        assert r.host_ports == [("a", 443), ("b", 443), ("c", 443)]

    def test_path_with_query(self):
        r = HttpLb.parse_url(
            "http://host:8000/path?key=val&other=2"
        )
        assert r.path == "/path?key=val&other=2"

    def test_empty_host_segment_ignored(self):
        """Trailing comma or double comma should not produce empty host entries."""
        r = HttpLb.parse_url("http://host1:8000,,host2:8001/path")
        assert r.host_ports == [("host1", 8000), ("host2", 8001)]

# ===================================================================
# HttpLb.build_timeout
# ===================================================================

class TestBuildTimeout:
    def test_all_defaults(self):
        t = HttpLb.build_timeout()
        assert t.connect == HttpLb.DEFAULT_CONNECT_TIMEOUT
        assert t.read == HttpLb.DEFAULT_READ_TIMEOUT
        assert t.write == HttpLb.DEFAULT_WRITE_TIMEOUT
        assert t.pool == HttpLb.DEFAULT_POOL_TIMEOUT

    def test_override_connect(self):
        t = HttpLb.build_timeout(connect=2.0)
        assert t.connect == 2.0
        assert t.read == HttpLb.DEFAULT_READ_TIMEOUT

    def test_override_read(self):
        t = HttpLb.build_timeout(read=600.0)
        assert t.read == 600.0
        assert t.connect == HttpLb.DEFAULT_CONNECT_TIMEOUT

    def test_override_all(self):
        t = HttpLb.build_timeout(
            connect=1.0, read=2.0, write=3.0, pool=4.0
        )
        assert t.connect == 1.0
        assert t.read == 2.0
        assert t.write == 3.0
        assert t.pool == 4.0


# ===================================================================
# HttpLb.create_shared_client
# ===================================================================

@pytest.mark.asyncio
class TestCreateSharedClient:
    async def test_default_client(self):
        client = HttpLb.create_shared_client()
        try:
            assert isinstance(client, httpx.AsyncClient)
            assert client.timeout.connect == HttpLb.DEFAULT_CONNECT_TIMEOUT
            assert client.timeout.read == HttpLb.DEFAULT_READ_TIMEOUT
            assert client.timeout.write == HttpLb.DEFAULT_WRITE_TIMEOUT
            assert client.timeout.pool == HttpLb.DEFAULT_POOL_TIMEOUT
        finally:
            await client.aclose()

    async def test_custom_timeouts(self):
        client = HttpLb.create_shared_client(
            connect_timeout=2.0, read_timeout=600.0,
        )
        try:
            assert client.timeout.connect == 2.0
            assert client.timeout.read == 600.0
            assert client.timeout.write == HttpLb.DEFAULT_WRITE_TIMEOUT
        finally:
            await client.aclose()

    async def test_custom_pool_limits(self):
        client = HttpLb.create_shared_client(
            max_connections=50,
            max_keepalive_connections=10,
            keepalive_expiry=60.0,
        )
        try:
            pool = client._transport._pool
            assert pool._max_connections == 50
            assert pool._max_keepalive_connections == 10
        finally:
            await client.aclose()

    async def test_as_context_manager(
        self, httpserver: pytest_httpserver.HTTPServer
    ):
        httpserver.expect_request(
            "/vcon", method="POST",
        ).respond_with_json({"ok": True})

        url = "http://{}:{}/vcon".format(httpserver.host, httpserver.port)
        async with HttpLb.create_shared_client() as client:
            resp = await HttpLb.post(
                url=url,
                body={"test": 1},
                content_type="application/json",
                client=client,
            )
        assert resp.status_code == 200


# ===================================================================
# HttpLb.resolve_host_ports
# ===================================================================

@pytest.mark.asyncio
class TestResolveHostPorts:
    async def test_localhost_resolves(self):
        results = await HttpLb.resolve_host_ports([("localhost", 8000)])
        assert len(results) >= 1
        for addr in results:
            assert addr.port == 8000
            assert addr.origin == "localhost"

    async def test_ip_passthrough(self):
        results = await HttpLb.resolve_host_ports([("127.0.0.1", 9999)])
        assert any(
            addr.ip == "127.0.0.1" and addr.port == 9999
            for addr in results
        )

    async def test_multiple_hosts(self):
        results = await HttpLb.resolve_host_ports([
            ("127.0.0.1", 8000), ("127.0.0.1", 8001),
        ])
        ports = {addr.port for addr in results}
        assert 8000 in ports and 8001 in ports

    async def test_unresolvable_host_skipped(self):
        results = await HttpLb.resolve_host_ports([
            ("this.host.does.not.exist.invalid", 1234),
            ("127.0.0.1", 8000),
        ])
        assert any(addr.port == 8000 for addr in results)

    async def test_shuffled(self):
        orders: typing.Set[tuple] = set()
        for _ in range(20):
            r = await HttpLb.resolve_host_ports([
                ("127.0.0.1", 1), ("127.0.0.1", 2),
            ])
            orders.add(tuple((a.ip, a.port) for a in r))
        assert len(orders) >= 2


@pytest.mark.asyncio
class TestResolveHostPortsEager:
    async def test_yields_results(self):
        results = []
        async for addr in HttpLb.resolve_host_ports_eager(
            [("127.0.0.1", 8000)]
        ):
            results.append(addr)
        assert len(results) >= 1

    async def test_multiple_hosts(self):
        results = []
        async for addr in HttpLb.resolve_host_ports_eager(
            [("127.0.0.1", 8000), ("127.0.0.1", 8001)]
        ):
            results.append(addr)
        ports = {addr.port for addr in results}
        assert 8000 in ports and 8001 in ports


# ===================================================================
# HttpLb.post_resolved_host (Layer 1)
# ===================================================================

@pytest.mark.asyncio
class TestPostResolvedHost:
    async def test_json_body(self, httpserver: pytest_httpserver.HTTPServer):
        httpserver.expect_request(
            "/test", method="POST",
        ).respond_with_json({"status": "ok"})

        resp = await HttpLb.post_resolved_host(
            scheme="http",
            host=httpserver.host,
            port=httpserver.port,
            path="/test",
            body={"hello": "world"},
            content_type="application/json",
        )
        assert resp.status_code == 200
        assert resp.json() == {"status": "ok"}

    async def test_raw_body(self, httpserver: pytest_httpserver.HTTPServer):
        httpserver.expect_request(
            "/raw", method="POST",
        ).respond_with_json({"received": True})

        resp = await HttpLb.post_resolved_host(
            scheme="http",
            host=httpserver.host,
            port=httpserver.port,
            path="/raw",
            body=b'raw bytes',
            content_type="application/octet-stream",
        )
        assert resp.status_code == 200

    async def test_no_body(self, httpserver: pytest_httpserver.HTTPServer):
        httpserver.expect_request(
            "/empty", method="POST",
        ).respond_with_json({"empty": True})

        resp = await HttpLb.post_resolved_host(
            scheme="http",
            host=httpserver.host,
            port=httpserver.port,
            path="/empty",
        )
        assert resp.status_code == 200

    async def test_with_password(self, httpserver: pytest_httpserver.HTTPServer):
        import base64
        expected = base64.b64encode(b":testpass").decode()

        httpserver.expect_request(
            "/secure", method="POST",
            headers={"Authorization": "Basic " + expected},
        ).respond_with_json({"auth": "ok"})

        resp = await HttpLb.post_resolved_host(
            scheme="http",
            host=httpserver.host,
            port=httpserver.port,
            path="/secure",
            body={"data": 1},
            content_type="application/json",
            password="testpass",
        )
        assert resp.status_code == 200

    async def test_shared_client(
        self, httpserver: pytest_httpserver.HTTPServer
    ):
        httpserver.expect_request(
            "/shared", method="POST",
        ).respond_with_json({"shared": True})

        async with httpx.AsyncClient() as client:
            resp = await HttpLb.post_resolved_host(
                scheme="http",
                host=httpserver.host,
                port=httpserver.port,
                path="/shared",
                body={"t": 1},
                content_type="application/json",
                client=client,
            )
        assert resp.status_code == 200

    async def test_connection_error_raises(self):
        with pytest.raises(Exception):
            await HttpLb.post_resolved_host(
                scheme="http",
                host="127.0.0.1",
                port=1,
                path="/nope",
                body=b"x",
            )


    async def test_sni_origin_sets_host_header(
        self, httpserver: pytest_httpserver.HTTPServer
      ):
        """
        When origin differs from host, the Host header should reflect
        the origin hostname, not the raw IP.
        """
        httpserver.expect_request(
            "/test", method="POST",
            headers={"Host": "myserver.example.com"},
        ).respond_with_json({"sni": "ok"})

        resp = await HttpLb.post_resolved_host(
            scheme="http",
            host=httpserver.host,
            port=httpserver.port,
            path="/test",
            body={"x": 1},
            content_type="application/json",
            origin="myserver.example.com",
        )
        assert resp.status_code == 200


# ===================================================================
# HttpLb.post (Layer 3 – load balanced)
# ===================================================================

@pytest.mark.asyncio
class TestPost:
    async def test_single_host_success(
        self, httpserver: pytest_httpserver.HTTPServer
    ):
        httpserver.expect_request(
            "/vcon", method="POST",
        ).respond_with_json({"ok": True})

        url = "http://{}:{}/vcon".format(httpserver.host, httpserver.port)
        resp = await HttpLb.post(
            url=url,
            body={"test": 1},
            content_type="application/json",
        )
        assert resp.status_code == 200

    async def test_failover_to_second_host(
        self, httpserver: pytest_httpserver.HTTPServer
    ):
        httpserver.expect_request(
            "/vcon", method="POST",
        ).respond_with_json({"ok": True})

        url = "http://127.0.0.1:1,{}:{}/vcon".format(
            httpserver.host, httpserver.port
        )
        resp = await HttpLb.post(
            url=url,
            body={"test": "failover"},
            content_type="application/json",
            connect_timeout=1.0,
            eager_resolve=False,
        )
        assert resp.status_code == 200

    async def test_all_hosts_fail_raises(self):
        url = "http://127.0.0.1:1,127.0.0.1:2/vcon"
        with pytest.raises(Exception, match="All hosts failed"):
            await HttpLb.post(
                url=url,
                body={"test": 1},
                content_type="application/json",
                connect_timeout=1.0,
            )

    async def test_password_forwarded(
        self, httpserver: pytest_httpserver.HTTPServer
    ):
        import base64
        expected = base64.b64encode(b":s3cret").decode()

        httpserver.expect_request(
            "/master", method="POST",
            headers={"Authorization": "Basic " + expected},
        ).respond_with_json({"ok": True})

        url = "http://:s3cret@{}:{}/master?db=0".format(
            httpserver.host, httpserver.port
        )
        resp = await HttpLb.post(
            url=url,
            body={"data": 1},
            content_type="application/json",
        )
        assert resp.status_code == 200

    async def test_eager_resolve(
        self, httpserver: pytest_httpserver.HTTPServer
    ):
        httpserver.expect_request(
            "/vcon", method="POST",
        ).respond_with_json({"ok": True})

        url = "http://{}:{}/vcon".format(httpserver.host, httpserver.port)
        resp = await HttpLb.post(
            url=url,
            body={"test": 1},
            content_type="application/json",
            eager_resolve=True,
        )
        assert resp.status_code == 200

    async def test_retryable_503_exhausts_single_host(
        self, httpserver: pytest_httpserver.HTTPServer
    ):
        httpserver.expect_ordered_request(
            "/vcon", method="POST",
        ).respond_with_json({"error": "unavailable"}, status=503)

        url = "http://{}:{}/vcon".format(httpserver.host, httpserver.port)
        with pytest.raises(Exception, match="All hosts failed"):
            await HttpLb.post(
                url=url,
                body={"test": 1},
                content_type="application/json",
            )

    async def test_no_port_defaults_http(
        self, httpserver: pytest_httpserver.HTTPServer
    ):
        """URL with no port should default to 80 for http."""
        r = HttpLb.parse_url(
            "http://example.com/vcon"
        )
        assert r.host_ports == [("example.com", 80)]

    async def test_no_port_defaults_https(self):
        r = HttpLb.parse_url("https://example.com/vcon")
        assert r.host_ports == [("example.com", 443)]


# ===================================================================
# max_retries
# ===================================================================

@pytest.mark.asyncio
class TestMaxRetries:
    async def test_max_retries_limits_attempts(self):
        """With 2 unreachable hosts but max_retries=1, only 1 is tried."""
        url = "http://127.0.0.1:1,127.0.0.1:2/vcon"
        with pytest.raises(Exception, match="attempted 1") as exc_info:
            await HttpLb.post(
                url=url,
                body={"test": 1},
                content_type="application/json",
                connect_timeout=1.0,
                max_retries=1,
            )

    async def test_max_retries_none_tries_all(self):
        """max_retries=None (default) tries every resolved address."""
        url = "http://127.0.0.1:1,127.0.0.1:2/vcon"
        with pytest.raises(Exception, match="attempted 2"):
            await HttpLb.post(
                url=url,
                body={"test": 1},
                content_type="application/json",
                connect_timeout=1.0,
                max_retries=None,
            )

    async def test_max_retries_success_before_limit(
        self, httpserver: pytest_httpserver.HTTPServer
    ):
        """Succeeds on second host with max_retries=3."""
        httpserver.expect_request(
            "/vcon", method="POST",
        ).respond_with_json({"ok": True})

        url = "http://127.0.0.1:1,{}:{}/vcon".format(
            httpserver.host, httpserver.port
        )
        resp = await HttpLb.post(
            url=url,
            body={"test": 1},
            content_type="application/json",
            connect_timeout=1.0,
            max_retries=3,
            eager_resolve=False,
        )
        assert resp.status_code == 200


# ===================================================================
# Timeout – actually validated against server delay
# ===================================================================

@pytest.mark.asyncio
class TestTimeoutValidation:

    async def test_read_timeout_fires_on_slow_response(
        self, httpserver: pytest_httpserver.HTTPServer
    ):
        """
        Server takes 4 s to respond.  read_timeout=2 should cause
        a ReadTimeout, and wall-clock should be ~2 s, not 4 s.
        """
        import time
        from werkzeug import Response

        def slow_handler(request):
            time.sleep(4)
            return Response(
                '{"ok":true}', status=200,
                content_type="application/json",
            )

        httpserver.expect_request(
            "/slow", method="POST",
        ).respond_with_handler(slow_handler)

        url = "http://{}:{}/slow".format(httpserver.host, httpserver.port)

        start = time.monotonic()
        with pytest.raises(Exception, match="All hosts failed"):
            await HttpLb.post(
                url=url,
                body={"test": 1},
                content_type="application/json",
                read_timeout=2.0,
            )
        elapsed = time.monotonic() - start
        # Should have given up around 2 s, well before the 4 s response
        assert elapsed < 3.5, "Expected ~2 s, got {:.1f} s".format(elapsed)
        assert elapsed >= 1.5, "Too fast ({:.1f} s), timeout may not have fired".format(elapsed)

    async def test_read_timeout_succeeds_when_server_is_fast_enough(
        self, httpserver: pytest_httpserver.HTTPServer
    ):
        """Server takes 1 s; read_timeout=5 should succeed."""
        import time
        from werkzeug import Response

        def slightly_slow(request):
            time.sleep(1)
            return Response(
                '{"ok":true}', status=200,
                content_type="application/json",
            )

        httpserver.expect_request(
            "/medium", method="POST",
        ).respond_with_handler(slightly_slow)

        url = "http://{}:{}/medium".format(httpserver.host, httpserver.port)
        start = time.monotonic()
        resp = await HttpLb.post(
            url=url,
            body={"test": 1},
            content_type="application/json",
            read_timeout=5.0,
        )
        elapsed = time.monotonic() - start
        assert resp.status_code == 200
        assert elapsed >= 0.8, "Server should have delayed ~1 s"
        assert elapsed < 4.0, "Took too long ({:.1f} s)".format(elapsed)

    async def test_connect_timeout_fast_failover(self):
        """
        Simulate a connect timeout using a mock.  read_timeout=300
        should be irrelevant; the connect_timeout should govern.
        """
        import time
        from unittest.mock import patch

        async def fake_resolve(host, port):
            return [ResolvedAddress("10.255.255.1", port, host)]

        async def fake_request(method, scheme, host, port, path, **kwargs):
            # Simulate a connect timeout after connect_timeout seconds
            ct = kwargs.get("connect_timeout", HttpLb.DEFAULT_CONNECT_TIMEOUT)
            await asyncio.sleep(ct)
            raise httpx.ConnectTimeout("simulated timeout")

        with patch.object(
            HttpLb, "_resolve_single", side_effect=fake_resolve
        ), patch.object(
            HttpLb, "_request_resolved_host", side_effect=fake_request
        ):
            start = time.monotonic()
            with pytest.raises(Exception, match="All hosts failed"):
                await HttpLb.post(
                    url="http://timeout.example.com:8000/vcon",
                    body={"test": 1},
                    content_type="application/json",
                    connect_timeout=1.0,
                    read_timeout=300.0,
                )
            elapsed = time.monotonic() - start

        # Should complete in ~1 s (connect_timeout), not 300 s (read)
        assert elapsed < 3.0, (
            "Expected ~1 s, got {:.1f} s".format(elapsed)
        )
        assert elapsed >= 0.8, (
            "Too fast ({:.1f} s), timeout may not have fired".format(elapsed)
        )

    async def test_read_timeout_does_not_cut_fast_connect(
        self, httpserver: pytest_httpserver.HTTPServer
    ):
        """
        A long read_timeout should not interfere when the server
        responds immediately.
        """
        httpserver.expect_request(
            "/fast", method="POST",
        ).respond_with_json({"ok": True})

        url = "http://{}:{}/fast".format(httpserver.host, httpserver.port)
        resp = await HttpLb.post(
            url=url,
            body={"test": 1},
            content_type="application/json",
            connect_timeout=2.0,
            read_timeout=600.0,
        )
        assert resp.status_code == 200


# ===================================================================
# Multi-record DNS resolution (mocked getaddrinfo)
# ===================================================================

@pytest.mark.asyncio
class TestMultiRecordDns:
    """
    Patch ``_resolve_single`` to simulate hostnames that expand to
    multiple A/AAAA records — something we cannot reliably test with
    real DNS in CI.
    """

    async def test_single_host_multiple_a_records(self):
        """One hostname returns 3 IPs; all should appear in results."""
        from unittest.mock import AsyncMock, patch

        fake_records = [
            ResolvedAddress("10.0.0.1", 8000, "multi.example.com"),
            ResolvedAddress("10.0.0.2", 8000, "multi.example.com"),
            ResolvedAddress("10.0.0.3", 8000, "multi.example.com"),
        ]

        with patch.object(
            HttpLb, "_resolve_single",
            new_callable=AsyncMock,
            return_value=fake_records,
        ):
            results = await HttpLb.resolve_host_ports(
                [("multi.example.com", 8000)]
            )

        assert len(results) == 3
        ips = {addr.ip for addr in results}
        assert ips == {"10.0.0.1", "10.0.0.2", "10.0.0.3"}
        # All should carry the origin
        assert all(addr.origin == "multi.example.com" for addr in results)

    async def test_two_hosts_each_multiple_records(self):
        """Two hostnames, each with 2 records = 4 total addresses."""
        from unittest.mock import AsyncMock, patch

        call_count = 0

        async def fake_resolve(host, port):
            nonlocal call_count
            call_count += 1
            if host == "alpha.example.com":
                return [
                    ResolvedAddress("10.0.0.1", port, host),
                    ResolvedAddress("10.0.0.2", port, host),
                ]
            else:
                return [
                    ResolvedAddress("10.0.1.1", port, host),
                    ResolvedAddress("10.0.1.2", port, host),
                ]

        with patch.object(
            HttpLb, "_resolve_single", side_effect=fake_resolve,
        ):
            results = await HttpLb.resolve_host_ports([
                ("alpha.example.com", 8000),
                ("beta.example.com", 9000),
            ])

        assert call_count == 2
        assert len(results) == 4
        ips = {addr.ip for addr in results}
        assert ips == {"10.0.0.1", "10.0.0.2", "10.0.1.1", "10.0.1.2"}
        # Check origins are preserved
        alpha_addrs = [a for a in results if a.origin == "alpha.example.com"]
        beta_addrs = [a for a in results if a.origin == "beta.example.com"]
        assert len(alpha_addrs) == 2
        assert len(beta_addrs) == 2

    async def test_multi_record_shuffled(self):
        """Results from multi-record resolution should be shuffled."""
        from unittest.mock import AsyncMock, patch

        records = [
            ResolvedAddress(f"10.0.0.{i}", 8000, "many.example.com")
            for i in range(10)
        ]

        orders_seen: typing.Set[tuple] = set()
        for _ in range(30):
            with patch.object(
                HttpLb, "_resolve_single",
                new_callable=AsyncMock,
                return_value=list(records),
            ):
                results = await HttpLb.resolve_host_ports(
                    [("many.example.com", 8000)]
                )
            orders_seen.add(tuple(addr.ip for addr in results))

        # With 10 items and 30 runs, we should see multiple orderings
        assert len(orders_seen) >= 2

    async def test_failover_across_multi_record_ips(
        self, httpserver: pytest_httpserver.HTTPServer
    ):
        """
        Hostname resolves to 3 IPs.  First two are dead
        (port 1, port 2), third is the real httpserver.
        Failover should reach the working one.
        """
        from unittest.mock import patch

        httpserver.expect_request(
            "/vcon", method="POST",
        ).respond_with_json({"ok": True})

        origin = "multi.example.com"
        fake_records = [
            ResolvedAddress("127.0.0.1", 1, origin),       # dead
            ResolvedAddress("127.0.0.1", 2, origin),       # dead
            ResolvedAddress(httpserver.host, httpserver.port, origin),
        ]

        async def fake_resolve(host, port):
            return list(fake_records)

        with patch.object(
            HttpLb, "_resolve_single", side_effect=fake_resolve,
        ):
            resp = await HttpLb.post(
                url="http://multi.example.com/vcon",
                body={"test": 1},
                content_type="application/json",
                connect_timeout=1.0,
                eager_resolve=False,
            )

        assert resp.status_code == 200

    async def test_all_multi_record_ips_dead(self):
        """All 3 resolved IPs are unreachable; should raise."""
        from unittest.mock import patch

        origin = "multi.example.com"
        fake_records = [
            ResolvedAddress("127.0.0.1", 1, origin),
            ResolvedAddress("127.0.0.1", 2, origin),
            ResolvedAddress("127.0.0.1", 3, origin),
        ]

        async def fake_resolve(host, port):
            return list(fake_records)

        with patch.object(
            HttpLb, "_resolve_single", side_effect=fake_resolve,
        ):
            with pytest.raises(Exception, match="attempted 3"):
                await HttpLb.post(
                    url="http://multi.example.com/vcon",
                    body={"test": 1},
                    content_type="application/json",
                    connect_timeout=1.0,
                )

    async def test_max_retries_with_multi_record(self):
        """max_retries=2 with 5 resolved IPs should only try 2."""
        from unittest.mock import patch

        origin = "multi.example.com"
        fake_records = [
            ResolvedAddress("127.0.0.1", i, origin) for i in range(1, 6)
        ]

        async def fake_resolve(host, port):
            return list(fake_records)

        with patch.object(
            HttpLb, "_resolve_single", side_effect=fake_resolve,
        ):
            with pytest.raises(Exception, match="attempted 2"):
                await HttpLb.post(
                    url="http://multi.example.com/vcon",
                    body={"test": 1},
                    content_type="application/json",
                    connect_timeout=1.0,
                    max_retries=2,
                )

    async def test_error_messages_show_origin(self):
        """
        When failover fails, error messages should include the
        original hostname, not just the resolved IP.
        """
        from unittest.mock import patch

        origin = "myserver.example.com"
        fake_records = [
            ResolvedAddress("10.0.0.1", 1, origin),
        ]

        async def fake_resolve(host, port):
            return list(fake_records)

        async def fake_request(*args, **kwargs):
            raise httpx.ConnectError("connection refused")

        with patch.object(
            HttpLb, "_resolve_single", side_effect=fake_resolve,
        ), patch.object(
            HttpLb, "_request_resolved_host", side_effect=fake_request,
        ):
            with pytest.raises(Exception) as exc_info:
                await HttpLb.post(
                    url="http://myserver.example.com/vcon",
                    body={"test": 1},
                    content_type="application/json",
                    connect_timeout=1.0,
                )
        # Error should contain both the origin hostname and the IP
        error_text = str(exc_info.value)
        assert "myserver.example.com" in error_text
        assert "10.0.0.1" in error_text


# ===================================================================
# Eager resolution – prove HTTP starts before all DNS completes
# ===================================================================

@pytest.mark.asyncio
class TestEagerResolution:
    """
    Verify that eager_resolve=True actually starts HTTP requests
    while DNS queries for other hosts are still in flight.
    """

    async def test_http_request_before_slow_dns_completes(
        self, httpserver: pytest_httpserver.HTTPServer
    ):
        """
        Two hosts in the URL.  fast_host resolves immediately;
        slow_host takes 3 s to resolve (and returns a dead IP anyway).

        With eager_resolve=True, the POST to fast_host's resolved IP
        should succeed *before* slow_host's DNS completes.
        Total wall-clock should be ~0 s (fast resolve + fast HTTP),
        NOT ~3 s (waiting for slow DNS).
        """
        import time
        from unittest.mock import patch

        httpserver.expect_request(
            "/vcon", method="POST",
        ).respond_with_json({"ok": True})

        slow_dns_complete_time = None

        async def fake_resolve(host, port):
            nonlocal slow_dns_complete_time
            if "slow" in host:
                await asyncio.sleep(3.0)
                slow_dns_complete_time = time.monotonic()
                return [ResolvedAddress("127.0.0.1", 1, host)]
            else:
                return [ResolvedAddress(
                    httpserver.host, httpserver.port, host
                )]

        with patch.object(
            HttpLb, "_resolve_single", side_effect=fake_resolve,
        ):
            start = time.monotonic()
            resp = await HttpLb.post(
                url="http://fast.example.com,slow.example.com/vcon",
                body={"test": 1},
                content_type="application/json",
                eager_resolve=True,
            )
            end = time.monotonic()

        assert resp.status_code == 200

        # The request should have completed FAST – well under the 3 s
        # that slow DNS takes.
        elapsed = end - start
        assert elapsed < 2.0, (
            "Request took {:.1f} s; should have completed before "
            "slow DNS (3 s) if eager mode is working".format(elapsed)
        )

    async def test_eager_vs_batch_timing(
        self, httpserver: pytest_httpserver.HTTPServer
    ):
        """
        Compare eager vs batch mode.  With one fast host and one
        3 s-slow host, eager should complete in <2 s while batch
        would take >=3 s (it waits for all DNS first).
        """
        import time
        from unittest.mock import patch

        httpserver.expect_request(
            "/vcon", method="POST",
        ).respond_with_json({"ok": True})

        async def fake_resolve(host, port):
            if "slow" in host:
                await asyncio.sleep(3.0)
                return [ResolvedAddress("127.0.0.1", 1, host)]
            return [ResolvedAddress(
                httpserver.host, httpserver.port, host
            )]

        # -- eager mode --
        with patch.object(
            HttpLb, "_resolve_single", side_effect=fake_resolve,
        ):
            start = time.monotonic()
            resp = await HttpLb.post(
                url="http://fast.example.com,slow.example.com/vcon",
                body={"test": 1},
                content_type="application/json",
                eager_resolve=True,
            )
            eager_elapsed = time.monotonic() - start

        assert resp.status_code == 200

        # Reset handler for second request
        httpserver.expect_request(
            "/vcon", method="POST",
        ).respond_with_json({"ok": True})

        # -- batch mode --
        with patch.object(
            HttpLb, "_resolve_single", side_effect=fake_resolve,
        ):
            start = time.monotonic()
            resp = await HttpLb.post(
                url="http://fast.example.com,slow.example.com/vcon",
                body={"test": 1},
                content_type="application/json",
                eager_resolve=False,
            )
            batch_elapsed = time.monotonic() - start

        assert resp.status_code == 200

        # Eager should be significantly faster than batch
        assert eager_elapsed < 2.0, (
            "Eager took {:.1f} s (expected <2 s)".format(eager_elapsed)
        )
        assert batch_elapsed >= 2.5, (
            "Batch took only {:.1f} s (expected >=3 s since it waits "
            "for all DNS)".format(batch_elapsed)
        )

    async def test_eager_tries_first_resolved_immediately(
        self, httpserver: pytest_httpserver.HTTPServer
    ):
        """
        Track the exact moment the HTTP server receives the request
        vs. when the slow DNS completes.  The HTTP hit should arrive
        *before* slow DNS returns.
        """
        import time
        from werkzeug import Response
        from unittest.mock import patch

        http_hit_time = None

        def recording_handler(request):
            nonlocal http_hit_time
            http_hit_time = time.monotonic()
            return Response(
                '{"ok":true}', status=200,
                content_type="application/json",
            )

        httpserver.expect_request(
            "/vcon", method="POST",
        ).respond_with_handler(recording_handler)

        slow_dns_done_time = None

        async def fake_resolve(host, port):
            nonlocal slow_dns_done_time
            if "slow" in host:
                await asyncio.sleep(3.0)
                slow_dns_done_time = time.monotonic()
                return [ResolvedAddress("127.0.0.1", 1, host)]
            return [ResolvedAddress(
                httpserver.host, httpserver.port, host
            )]

        with patch.object(
            HttpLb, "_resolve_single", side_effect=fake_resolve,
        ):
            resp = await HttpLb.post(
                url="http://fast.example.com,slow.example.com/vcon",
                body={"test": 1},
                content_type="application/json",
                eager_resolve=True,
            )

        assert resp.status_code == 200
        assert http_hit_time is not None, "Server never received the request"

        # The HTTP request should have arrived BEFORE slow DNS finished.
        # slow_dns_done_time may be None if the coroutine was cancelled
        # after the successful response.  Either way, the request hit
        # the server before slow DNS completed.
        if slow_dns_done_time is not None:
            assert http_hit_time < slow_dns_done_time, (
                "HTTP hit at {:.3f}, but slow DNS completed at {:.3f}. "
                "Eager mode should have sent the request before slow "
                "DNS returned.".format(http_hit_time, slow_dns_done_time)
            )

# ===================================================================
# HttpLb.get
# ===================================================================

@pytest.mark.asyncio
class TestGet:
    async def test_get_success(
        self, httpserver: pytest_httpserver.HTTPServer
    ):
        httpserver.expect_request(
            "/resource", method="GET",
        ).respond_with_json({"data": "hello"})

        url = "http://{}:{}/resource".format(
            httpserver.host, httpserver.port
        )
        resp = await HttpLb.get(url=url)
        assert resp.status_code == 200
        assert resp.json() == {"data": "hello"}

    async def test_get_no_body(
        self, httpserver: pytest_httpserver.HTTPServer
    ):
        """GET should not send a request body."""
        httpserver.expect_request(
            "/empty", method="GET",
        ).respond_with_json({"ok": True})

        url = "http://{}:{}/empty".format(
            httpserver.host, httpserver.port
        )
        resp = await HttpLb.get(url=url)
        assert resp.status_code == 200

    async def test_get_failover(
        self, httpserver: pytest_httpserver.HTTPServer
    ):
        httpserver.expect_request(
            "/resource", method="GET",
        ).respond_with_json({"ok": True})

        url = "http://127.0.0.1:1,{}:{}/resource".format(
            httpserver.host, httpserver.port
        )
        resp = await HttpLb.get(
            url=url,
            connect_timeout=1.0,
            eager_resolve=False,
        )
        assert resp.status_code == 200

    async def test_get_with_shared_client(
        self, httpserver: pytest_httpserver.HTTPServer
    ):
        httpserver.expect_request(
            "/resource", method="GET",
        ).respond_with_json({"ok": True})

        url = "http://{}:{}/resource".format(
            httpserver.host, httpserver.port
        )
        async with HttpLb.create_shared_client() as client:
            resp = await HttpLb.get(url=url, client=client)
        assert resp.status_code == 200

# ===================================================================
# HttpLb.put
# ===================================================================

@pytest.mark.asyncio
class TestPut:
    async def test_put_json(
        self, httpserver: pytest_httpserver.HTTPServer
    ):
        httpserver.expect_request(
            "/resource", method="PUT",
        ).respond_with_json({"updated": True})

        url = "http://{}:{}/resource".format(
            httpserver.host, httpserver.port
        )
        resp = await HttpLb.put(
            url=url,
            body={"key": "value"},
            content_type="application/json",
        )
        assert resp.status_code == 200
        assert resp.json() == {"updated": True}

    async def test_put_raw_body(
        self, httpserver: pytest_httpserver.HTTPServer
    ):
        httpserver.expect_request(
            "/raw", method="PUT",
        ).respond_with_json({"received": True})

        url = "http://{}:{}/raw".format(
            httpserver.host, httpserver.port
        )
        resp = await HttpLb.put(
            url=url,
            body=b"raw content",
            content_type="application/octet-stream",
        )
        assert resp.status_code == 200

    async def test_put_no_body(
        self, httpserver: pytest_httpserver.HTTPServer
    ):
        httpserver.expect_request(
            "/empty", method="PUT",
        ).respond_with_json({"ok": True})

        url = "http://{}:{}/empty".format(
            httpserver.host, httpserver.port
        )
        resp = await HttpLb.put(url=url)
        assert resp.status_code == 200

    async def test_put_failover(
        self, httpserver: pytest_httpserver.HTTPServer
    ):
        httpserver.expect_request(
            "/resource", method="PUT",
        ).respond_with_json({"ok": True})

        url = "http://127.0.0.1:1,{}:{}/resource".format(
            httpserver.host, httpserver.port
        )
        resp = await HttpLb.put(
            url=url,
            body={"test": 1},
            content_type="application/json",
            connect_timeout=1.0,
            eager_resolve=False,
        )
        assert resp.status_code == 200


# ===================================================================
# HttpLb.request (generic method dispatch)
# ===================================================================

@pytest.mark.asyncio
class TestRequest:
    async def test_request_post(
        self, httpserver: pytest_httpserver.HTTPServer
    ):
        httpserver.expect_request(
            "/vcon", method="POST",
        ).respond_with_json({"ok": True})

        url = "http://{}:{}/vcon".format(
            httpserver.host, httpserver.port
        )
        resp = await HttpLb.request(
            "POST", url,
            body={"test": 1},
            content_type="application/json",
        )
        assert resp.status_code == 200

    async def test_request_get(
        self, httpserver: pytest_httpserver.HTTPServer
    ):
        httpserver.expect_request(
            "/resource", method="GET",
        ).respond_with_json({"data": 1})

        url = "http://{}:{}/resource".format(
            httpserver.host, httpserver.port
        )
        resp = await HttpLb.request("GET", url)
        assert resp.status_code == 200

    async def test_request_put(
        self, httpserver: pytest_httpserver.HTTPServer
    ):
        httpserver.expect_request(
            "/resource", method="PUT",
        ).respond_with_json({"updated": True})

        url = "http://{}:{}/resource".format(
            httpserver.host, httpserver.port
        )
        resp = await HttpLb.request(
            "PUT", url,
            body={"key": "val"},
            content_type="application/json",
        )
        assert resp.status_code == 200

    async def test_request_delete(
        self, httpserver: pytest_httpserver.HTTPServer
    ):
        httpserver.expect_request(
            "/resource/123", method="DELETE",
        ).respond_with_json({"deleted": True})

        url = "http://{}:{}/resource/123".format(
            httpserver.host, httpserver.port
        )
        resp = await HttpLb.request("DELETE", url)
        assert resp.status_code == 200

    async def test_request_method_case_insensitive(
        self, httpserver: pytest_httpserver.HTTPServer
    ):
        """method string should be uppercased internally."""
        httpserver.expect_request(
            "/vcon", method="POST",
        ).respond_with_json({"ok": True})

        url = "http://{}:{}/vcon".format(
            httpserver.host, httpserver.port
        )
        resp = await HttpLb.request(
            "post", url,
            body={"test": 1},
            content_type="application/json",
        )
        assert resp.status_code == 200

    async def test_request_failover(
        self, httpserver: pytest_httpserver.HTTPServer
    ):
        httpserver.expect_request(
            "/vcon", method="PUT",
        ).respond_with_json({"ok": True})

        url = "http://127.0.0.1:1,{}:{}/vcon".format(
            httpserver.host, httpserver.port
        )
        resp = await HttpLb.request(
            "PUT", url,
            body={"test": "failover"},
            content_type="application/json",
            connect_timeout=1.0,
            eager_resolve=False,
        )
        assert resp.status_code == 200

    async def test_request_dynamic_method_from_string(
        self, httpserver: pytest_httpserver.HTTPServer
    ):
        """
        Simulate the __init__.py use case where method comes
        from a query parameter string.
        """
        httpserver.expect_request(
            "/queue/jobs", method="PUT",
        ).respond_with_json({"queued": True})

        # Simulate the event hook URL pattern
        event_url = "http://{}:{}/queue/jobs?method=PUT&body={{\"job\":\"test\"}}".format(
            httpserver.host, httpserver.port
        )

        import urllib.parse
        if '?' in event_url:
            base_url, query_string = event_url.split('?', 1)
            query_params = urllib.parse.parse_qs(query_string)
        else:
            base_url = event_url
            query_params = {}

        method = query_params['method'][0]
        body = query_params.get('body', [None])[0]
        content_type = "application/json" if body else None

        resp = await HttpLb.request(
            method,
            base_url,
            body=body,
            content_type=content_type,
        )
        assert resp.status_code == 200

    async def test_request_multi_host_url_not_mangled(
        self, httpserver: pytest_httpserver.HTTPServer
    ):
        """
        Verify that the split-on-? approach preserves
        comma-separated host:port pairs, unlike urlparse.
        """
        httpserver.expect_request(
            "/queue/jobs", method="PUT",
        ).respond_with_json({"ok": True})

        # Multi-host URL with query params
        event_url = (
            "http://127.0.0.1:1,{}:{}"
            "/queue/jobs?method=PUT&body={{\"x\":1}}"
        ).format(httpserver.host, httpserver.port)

        if '?' in event_url:
            base_url, query_string = event_url.split('?', 1)
            query_params = urllib.parse.parse_qs(query_string)
        else:
            base_url = event_url
            query_params = {}

        # base_url should still have the comma-separated hosts
        assert ',' in base_url

        method = query_params['method'][0]
        body = query_params.get('body', [None])[0]

        resp = await HttpLb.request(
            method,
            base_url,
            body=body,
            content_type="application/json",
            connect_timeout=1.0,
            eager_resolve=False,
        )
        assert resp.status_code == 200


@pytest.mark.asyncio
class TestRequestMethod:
    async def test_request_delete(
        self, httpserver: pytest_httpserver.HTTPServer
    ):
        httpserver.expect_request(
            "/resource/1", method="DELETE",
        ).respond_with_json({"deleted": True})

        url = "http://{}:{}/resource/1".format(httpserver.host, httpserver.port)
        resp = await HttpLb.request("DELETE", url)
        assert resp.status_code == 200

