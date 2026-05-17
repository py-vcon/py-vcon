# Copyright (C) 2023-2026 SIPez LLC.  All rights reserved.
"""
HTTP load balancing and failover utilities.

Provides multi-host URL support with DNS resolution, randomized load balancing,
and automatic failover on connection or server errors.

Supported URL formats::

  Single host:
    http://host:port/path
    http://host/path                           (port defaults for scheme)

  Multi-host with load balancing and failover:
    http://:password@host1:port1,host2:port2/path?query=value
    http://host1:port1,host2:port2/path
    http://host1,host2:port2/path              (host1 gets default port)

Hosts may be IP addresses or DNS names.  DNS names are resolved to all
A and AAAA records and the full set of resolved addresses is randomized
to provide load balancing.  If a request to one address fails with a
connection error or a retryable server error (502, 503, 504), the next
address in the shuffled list is tried.

Architecture (low to high):

  ParsedMultiHostUrl  - URL parsing and multi-host detection
  HttpLb              - DNS resolution, request execution, load balanced
                        failover, shared client creation
"""

import asyncio
import vcon.logging_utils
import random
import re
import socket
import typing

import httpx

logger = vcon.logging_utils.build_logger(__name__)


# HTTP status codes that suggest the *specific server* is unhealthy;
# worth retrying on a different host.
RETRYABLE_STATUS_CODES = frozenset({502, 503, 504})


class HttpLbConnectionError(Exception):
    """All resolved addresses failed with connection-level errors.

    Carries structured information about the failed attempt for
    programmatic access by callers (e.g. retry policies, error
    reporting).  The string form of the exception preserves the
    same human-readable message format as before so log output
    and substring-matching tests are unaffected.

    Attributes:
      method: HTTP method (e.g. "POST").
      url: original URL passed to HttpLb.
      attempts: number of addresses attempted.
      attempted_hosts: list of "host(ip):port" labels that were
          tried, in attempt order.
      errors: list of error-message strings, one per attempted
          address, parallel to attempted_hosts.
    """

    def __init__(
        self,
        method: str,
        url: str,
        attempts: int,
        attempted_hosts: typing.List[str],
        errors: typing.List[str],
        ) -> None:
        self.method = method
        self.url = url
        self.attempts = attempts
        self.attempted_hosts = list(attempted_hosts)
        self.errors = list(errors)
        super().__init__(self._format_message())

    def _format_message(self) -> str:
        if not self.errors:
            details = "(no resolved addresses)"
        else:
            details = "\n  ".join(self.errors)
        return (
            "All hosts failed for {method} {url} "
            "(attempted {n}).  Errors:\n  {details}".format(
                method=self.method,
                url=self.url,
                n=self.attempts,
                details=details,
            )
        )


# Exception types that indicate connection-level failures worth retrying.
RETRYABLE_EXCEPTIONS = (
    httpx.ConnectError,
    httpx.ConnectTimeout,
    httpx.ReadTimeout,
    httpx.WriteTimeout,
    httpx.PoolTimeout,
    ConnectionRefusedError,
    ConnectionResetError,
    OSError,
    HttpLbConnectionError,
)


# ---------------------------------------------------------------------------
# URL parsing
# ---------------------------------------------------------------------------

class ParsedMultiHostUrl(typing.NamedTuple):
    """Result of parsing a multi-host URL."""
    scheme: str
    password: typing.Optional[str]
    host_ports: typing.List[typing.Tuple[str, int]]
    path: str  # includes query string, e.g. "/master?db=0"


class ResolvedAddress(typing.NamedTuple):
    """A single resolved IP address with its origin hostname."""
    ip: str
    port: int
    origin: str  # original hostname before DNS resolution


# ---------------------------------------------------------------------------
# Load-balanced HTTP
# ---------------------------------------------------------------------------

class HttpLb:
    """
    Static methods for DNS-resolved, load-balanced, failover HTTP requests.

    All public methods are ``@staticmethod``; no instance is needed.
    """

    # -- timeout defaults (seconds) --
    DEFAULT_CONNECT_TIMEOUT: float = 5.0
    """TCP/TLS handshake.  Keep short for fast failover."""

    DEFAULT_READ_TIMEOUT: float = 300.0
    """Wait for response data.  Set high for LLM / transcription backends."""

    DEFAULT_WRITE_TIMEOUT: float = 20.0
    """Send request body."""

    DEFAULT_POOL_TIMEOUT: float = 10.0
    """Wait for a connection from the pool."""

    # -- connection pool defaults --
    DEFAULT_MAX_CONNECTIONS: int = 100
    DEFAULT_MAX_KEEPALIVE_CONNECTIONS: int = 20
    DEFAULT_KEEPALIVE_EXPIRY: float = 30.0

    # -- retry defaults --
    DEFAULT_MAX_RETRIES: typing.Optional[int] = None
    """Maximum number of addresses to attempt.  None = try all resolved."""

    # -----------------------------------------------------------------
    # URL parsing
    # -----------------------------------------------------------------

    @staticmethod
    def is_multi_host_url(url: str) -> bool:
        """
        Return True if *url* uses the comma-separated multi-host format.

        Quick heuristic: after stripping ``scheme://`` and any
        ``user:pass@`` prefix, the netloc portion contains a comma.
        """
        after_scheme = re.sub(r'^https?://', '', url)
        if '@' in after_scheme:
            after_scheme = after_scheme.split('@', 1)[1]
        netloc = after_scheme.split('/', 1)[0]
        return ',' in netloc

    @staticmethod
    def parse_url(url: str) -> ParsedMultiHostUrl:
        """
        Parse a URL that may contain comma-separated host:port pairs.

        When a port is omitted from a host, the default for the scheme
        is used (80 for http, 443 for https).

        Supported formats::

            http://host/path
            http://host:port/path
            http://:password@host1:port1,host2:port2/path?query
            https://host1:port1,host2/path

        Parameters:
          **url** (str): the URL string to parse.

        Returns:
          ``ParsedMultiHostUrl``

        Raises:
          ValueError: if the URL cannot be parsed.
        """
        match = re.match(
            r'^(https?)://'           # scheme
            r'(?::([^@]*)@)?'         # optional :password@  (user part empty)
            r'(.+?)'                  # host section (non-greedy)
            r'(/.*)$',                # path + query (must start with /)
            url
        )
        if match is None:
            match = re.match(
                r'^(https?)://'
                r'(?::([^@]*)@)?'
                r'(.+)$',
                url
            )
            if match is None:
                raise ValueError("Cannot parse URL: {}".format(url))
            scheme = match.group(1)
            password = match.group(2)
            host_section = match.group(3)
            path = '/'
        else:
            scheme = match.group(1)
            password = match.group(2)
            host_section = match.group(3)
            path = match.group(4)

        default_port = 443 if scheme == 'https' else 80
        host_ports: typing.List[typing.Tuple[str, int]] = []

        for hp in host_section.split(','):
            hp = hp.strip()
            if not hp:
                continue
            ipv6_match = re.match(r'^\[([^\]]+)\]:(\d+)$', hp)
            if ipv6_match:
                host_ports.append(
                    (ipv6_match.group(1), int(ipv6_match.group(2)))
                )
            elif ':' in hp:
                host, port_str = hp.rsplit(':', 1)
                try:
                    port = int(port_str)
                except ValueError:
                    host_ports.append((hp, default_port))
                    continue
                host_ports.append((host, port))
            else:
                host_ports.append((hp, default_port))

        if not host_ports:
            raise ValueError(
                "No host:port pairs found in URL: {}".format(url)
            )

        return ParsedMultiHostUrl(
            scheme=scheme,
            password=password,
            host_ports=host_ports,
            path=path,
        )

    # -----------------------------------------------------------------
    # Timeout helper
    # -----------------------------------------------------------------

    @staticmethod
    def build_timeout(
        connect: typing.Optional[float] = None,
        read: typing.Optional[float] = None,
        write: typing.Optional[float] = None,
        pool: typing.Optional[float] = None,
        ) -> httpx.Timeout:
        """
        Build an ``httpx.Timeout`` from individual overrides.

        Any parameter left as None falls back to the class default.

        Parameters:
          **connect** (float, optional): TCP/TLS timeout.
          **read** (float, optional): response data timeout.
          **write** (float, optional): request body send timeout.
          **pool** (float, optional): pool wait timeout.

        Returns:
          ``httpx.Timeout``
        """
        return httpx.Timeout(
            connect=(
                connect if connect is not None
                else HttpLb.DEFAULT_CONNECT_TIMEOUT
            ),
            read=(
                read if read is not None
                else HttpLb.DEFAULT_READ_TIMEOUT
            ),
            write=(
                write if write is not None
                else HttpLb.DEFAULT_WRITE_TIMEOUT
            ),
            pool=(
                pool if pool is not None
                else HttpLb.DEFAULT_POOL_TIMEOUT
            ),
        )

    # -----------------------------------------------------------------
    # Shared client factory
    # -----------------------------------------------------------------

    @staticmethod
    def create_shared_client(
        connect_timeout: typing.Optional[float] = None,
        read_timeout: typing.Optional[float] = None,
        write_timeout: typing.Optional[float] = None,
        pool_timeout: typing.Optional[float] = None,
        max_connections: typing.Optional[int] = None,
        max_keepalive_connections: typing.Optional[int] = None,
        keepalive_expiry: typing.Optional[float] = None,
        ) -> httpx.AsyncClient:
        """
        Create an ``httpx.AsyncClient`` configured for long-running
        server processes.

        The returned client should be stored at application startup
        and passed as the *client* argument to request methods for
        connection pooling and keep-alive reuse.

        The caller is responsible for closing the client on shutdown::

            client = HttpLb.create_shared_client(read_timeout=600)
            # ... use client ...
            await client.aclose()

        Or as an async context manager::

            async with HttpLb.create_shared_client() as client:
                ...

        Parameters:
          **connect_timeout** (float, optional): override connect.
          **read_timeout** (float, optional): override read.
          **write_timeout** (float, optional): override write.
          **pool_timeout** (float, optional): override pool wait.
          **max_connections** (int, optional): total concurrent
              connections (default: 100).
          **max_keepalive_connections** (int, optional): idle
              keep-alive connections (default: 20).
          **keepalive_expiry** (float, optional): idle connection
              lifetime in seconds (default: 30).

        Returns:
          ``httpx.AsyncClient``
        """
        timeout = HttpLb.build_timeout(
            connect=connect_timeout,
            read=read_timeout,
            write=write_timeout,
            pool=pool_timeout,
        )
        limits = httpx.Limits(
            max_connections=(
                max_connections
                if max_connections is not None
                else HttpLb.DEFAULT_MAX_CONNECTIONS
            ),
            max_keepalive_connections=(
                max_keepalive_connections
                if max_keepalive_connections is not None
                else HttpLb.DEFAULT_MAX_KEEPALIVE_CONNECTIONS
            ),
            keepalive_expiry=(
                keepalive_expiry
                if keepalive_expiry is not None
                else HttpLb.DEFAULT_KEEPALIVE_EXPIRY
            ),
        )
        return httpx.AsyncClient(timeout=timeout, limits=limits)

    # -----------------------------------------------------------------
    # DNS resolution (Layer 2)
    # -----------------------------------------------------------------

    @staticmethod
    async def _resolve_single(
        host: str,
        port: int,
        ) -> typing.List[ResolvedAddress]:
        """
        Resolve a single host to ``ResolvedAddress`` tuples (A + AAAA).

        Each result carries the original *host* as ``origin`` so that
        log messages can show which DNS name produced a given IP.

        Results are shuffled before returning.
        """
        loop = asyncio.get_running_loop()
        try:
            infos = await loop.getaddrinfo(
                host, port,
                family=socket.AF_UNSPEC,
                type=socket.SOCK_STREAM,
            )
        except socket.gaierror as exc:
            logger.warning(
                "DNS resolution failed for %s:%s – %s", host, port, exc
            )
            return []

        seen: typing.Set[typing.Tuple[str, int]] = set()
        results: typing.List[ResolvedAddress] = []
        for family, _type, _proto, _canonname, sockaddr in infos:
            ip = sockaddr[0]
            pair = (ip, port)
            if pair not in seen:
                seen.add(pair)
                results.append(ResolvedAddress(ip=ip, port=port, origin=host))

        random.shuffle(results)
        return results

    @staticmethod
    async def resolve_host_ports(
        host_port_pairs: typing.List[typing.Tuple[str, int]],
        ) -> typing.List[ResolvedAddress]:
        """
        Resolve a list of ``(hostname, port)`` pairs to a flat,
        shuffled list of ``ResolvedAddress`` tuples.

        All DNS look-ups run concurrently.  Each hostname may expand
        to multiple A/AAAA records.  The combined result is shuffled.

        Parameters:
          **host_port_pairs** (list of (str, int)):
              hostnames or IPs with their ports.

        Returns:
          list of ``ResolvedAddress`` tuples, randomly ordered.
        """
        tasks = [
            asyncio.create_task(HttpLb._resolve_single(host, port))
            for host, port in host_port_pairs
        ]
        gathered = await asyncio.gather(*tasks)

        all_resolved: typing.List[ResolvedAddress] = []
        for result_list in gathered:
            all_resolved.extend(result_list)

        random.shuffle(all_resolved)
        return all_resolved

    @staticmethod
    async def resolve_host_ports_eager(
        host_port_pairs: typing.List[typing.Tuple[str, int]],
        ) -> typing.AsyncGenerator[ResolvedAddress, None]:
        """
        Like :meth:`resolve_host_ports` but yields ``ResolvedAddress``
        tuples as soon as each DNS look-up completes, allowing
        connection attempts to begin while other queries are still
        in flight.

        Parameters:
          **host_port_pairs** (list of (str, int)):
              hostnames or IPs with their ports.

        Yields:
          ``ResolvedAddress`` tuples.
        """
        tasks = {
            asyncio.ensure_future(
                HttpLb._resolve_single(host, port)
            ): (host, port)
            for host, port in host_port_pairs
        }
        for coro in asyncio.as_completed(tasks.keys()):
            resolved = await coro
            for pair in resolved:
                yield pair

    # -----------------------------------------------------------------
    # Single-host request (Layer 1)
    # -----------------------------------------------------------------

    @staticmethod
    async def _request_resolved_host(
        method: str,
        scheme: str,
        host: str,
        port: int,
        path: str,
        body: typing.Any = None,
        content_type: typing.Optional[str] = None,
        headers: typing.Optional[typing.Dict[str, str]] = None,
        password: typing.Optional[str] = None,
        follow_redirects: bool = True,
        connect_timeout: typing.Optional[float] = None,
        read_timeout: typing.Optional[float] = None,
        write_timeout: typing.Optional[float] = None,
        pool_timeout: typing.Optional[float] = None,
        client: typing.Optional[httpx.AsyncClient] = None,
        origin: typing.Optional[str] = None,
        ) -> httpx.Response:
        """
        Send an HTTP request to a single, already-resolved host.

        Parameters:
          **method** (str): HTTP method (``"POST"``, ``"GET"``, etc.).
          **scheme** (str): ``"http"`` or ``"https"``.
          **host** (str): resolved IP address or hostname.
          **port** (int): TCP port.
          **path** (str): URL path including any query string.
          **body** (optional): request body.  If *content_type*
              contains ``"json"`` and *body* is a ``dict`` or
              ``list``, the body is JSON-serialized via httpx.
              Otherwise it is sent as raw content.
          **content_type** (str, optional): ``Content-Type`` header
              value.  Also controls JSON serialization (see *body*).
          **headers** (dict, optional): additional HTTP headers.
          **password** (str, optional): HTTP Basic auth with empty
              username.
          **follow_redirects** (bool): follow 3xx (default True).
          **connect_timeout** (float, optional): TCP/TLS timeout.
          **read_timeout** (float, optional): response data timeout.
          **write_timeout** (float, optional): send body timeout.
          **pool_timeout** (float, optional): pool wait timeout.
          **client** (httpx.AsyncClient, optional): shared client for
              connection pooling.
          **origin** (str, optional): original hostname before DNS
              resolution.  When *host* is a raw IP and *scheme* is
              ``"https"``, this is passed as the TLS SNI hostname so
              that certificate validation uses the correct name rather
              than the IP address.

        Returns:
          ``httpx.Response``
        """
        # Build URL; bracket IPv6 literals.
        if ':' in host and not host.startswith('['):
            host_part = '[{}]'.format(host)
        else:
            host_part = host

        url = "{scheme}://{host}:{port}{path}".format(
            scheme=scheme,
            host=host_part,
            port=port,
            path=path,
        )

        effective_timeout = HttpLb.build_timeout(
            connect=connect_timeout,
            read=read_timeout,
            write=write_timeout,
            pool=pool_timeout,
        )

        kwargs: typing.Dict[str, typing.Any] = {
            "timeout": effective_timeout,
            "follow_redirects": follow_redirects,
        }

        sni_host = origin if (origin and origin != host) else None
        if sni_host and scheme == "https":
            kwargs["extensions"] = {"sni_hostname": sni_host}

        # Headers – merge content_type into caller-supplied headers.
        merged_headers: typing.Dict[str, str] = {}
        if headers:
            merged_headers.update(headers)
        if content_type is not None:
            merged_headers["Content-Type"] = content_type
        if sni_host:
            merged_headers.setdefault("Host", sni_host)
        if merged_headers:
            kwargs["headers"] = merged_headers

        if password is not None:
            kwargs["auth"] = httpx.BasicAuth(
                username="", password=password
            )

        # Body handling.
        if body is not None:
            use_json = (
                content_type is not None
                and "json" in content_type
                and isinstance(body, (dict, list))
            )
            if use_json:
                kwargs["json"] = body
            else:
                kwargs["content"] = body

        logger.debug(
            "%s %s (timeout connect=%.1f read=%.1f write=%.1f pool=%.1f)",
            method, url,
            effective_timeout.connect, effective_timeout.read,
            effective_timeout.write, effective_timeout.pool,
        )

        if client is not None:
            return await client.request(method, url, **kwargs)
        else:
            async with httpx.AsyncClient() as c:
                return await c.request(method, url, **kwargs)

    @staticmethod
    async def post_resolved_host(
        scheme: str,
        host: str,
        port: int,
        path: str,
        body: typing.Any = None,
        content_type: typing.Optional[str] = None,
        headers: typing.Optional[typing.Dict[str, str]] = None,
        password: typing.Optional[str] = None,
        follow_redirects: bool = True,
        connect_timeout: typing.Optional[float] = None,
        read_timeout: typing.Optional[float] = None,
        write_timeout: typing.Optional[float] = None,
        pool_timeout: typing.Optional[float] = None,
        client: typing.Optional[httpx.AsyncClient] = None,
        origin: typing.Optional[str] = None
        ) -> httpx.Response:
        """
        HTTP POST to a single, already-resolved host.

        Convenience wrapper around :meth:`_request_resolved_host`.
        See that method for full parameter documentation.
        """
        return await HttpLb._request_resolved_host(
            "POST", scheme, host, port, path,
            body=body, content_type=content_type, headers=headers,
            password=password, follow_redirects=follow_redirects,
            connect_timeout=connect_timeout, read_timeout=read_timeout,
            write_timeout=write_timeout, pool_timeout=pool_timeout,
            client=client,
            origin=origin
        )

    # -----------------------------------------------------------------
    # Load-balanced request (Layer 3)
    # -----------------------------------------------------------------

    @staticmethod
    async def _request_with_loadbalance(
        method: str,
        url: str,
        body: typing.Any = None,
        content_type: typing.Optional[str] = None,
        headers: typing.Optional[typing.Dict[str, str]] = None,
        follow_redirects: bool = True,
        connect_timeout: typing.Optional[float] = None,
        read_timeout: typing.Optional[float] = None,
        write_timeout: typing.Optional[float] = None,
        pool_timeout: typing.Optional[float] = None,
        max_retries: typing.Optional[int] = None,
        eager_resolve: bool = True,
        client: typing.Optional[httpx.AsyncClient] = None,
        ) -> httpx.Response:
        """
        Parse a (possibly multi-host) URL, resolve DNS, and send an
        HTTP request with automatic load balancing and failover.

        **Load balancing**: resolved addresses are shuffled so that
        successive calls distribute traffic across hosts.

        **Failover**: each resolved address is tried in turn;
        connection errors and retryable HTTP status codes
        (502, 503, 504) advance to the next address.

        **Redirects**: followed within each attempt (controlled by
        *follow_redirects*).

        Parameters:
          **method** (str): HTTP method (``"POST"``, ``"GET"``, etc.).
          **url** (str): single-host or multi-host URL.
              ``http://:pw@h1:8000,h2:8001/path?db=0``
          **body** (optional): request body.  See
              :meth:`_request_resolved_host` for JSON handling.
          **content_type** (str, optional): ``Content-Type`` header.
          **headers** (dict, optional): additional HTTP headers.
          **follow_redirects** (bool): follow 3xx (default True).
          **connect_timeout** (float, optional): TCP/TLS timeout.
          **read_timeout** (float, optional): response data timeout.
          **write_timeout** (float, optional): send body timeout.
          **pool_timeout** (float, optional): pool wait timeout.
          **max_retries** (int, optional): maximum number of
              addresses to attempt.  ``None`` (default) means try
              every resolved address.
          **eager_resolve** (bool): if True (default), start trying
              hosts as DNS results arrive; if False, wait for all
              DNS look-ups first.
          **client** (httpx.AsyncClient, optional): shared client.

        Returns:
          ``httpx.Response`` from the first successful attempt.

        Raises:
          ``HttpLbConnectionError`` if all attempts fail.  Carries
          ``method``, ``url``, ``attempts``, ``attempted_hosts``, and
          ``errors`` attributes for programmatic access.
        """
        parsed = HttpLb.parse_url(url)

        effective_max = (
            max_retries
            if max_retries is not None
            else HttpLb.DEFAULT_MAX_RETRIES
        )

        # Shuffle host:port pairs before DNS resolution so URL
        # ordering does not bias which host is tried first.
        # Critical for eager mode where as_completed tends to
        # return the first-submitted query first.
        shuffled = list(parsed.host_ports)
        random.shuffle(shuffled)

        errors: typing.List[str] = []
        attempted_hosts: typing.List[str] = []
        attempts = 0

        def _format_host(addr: ResolvedAddress) -> str:
            """Format address for log/error messages, showing origin if different from IP."""
            if addr.origin != addr.ip:
                return "{}({})".format(addr.origin, addr.ip)
            return addr.ip

        async def _try_host(
            addr: ResolvedAddress
            ) -> typing.Optional[httpx.Response]:
            nonlocal attempts
            if effective_max is not None and attempts >= effective_max:
                return None

            attempts += 1
            host_label = _format_host(addr)
            try:
                resp = await HttpLb._request_resolved_host(
                    method, parsed.scheme, addr.ip, addr.port, parsed.path,
                    body=body, content_type=content_type,
                    headers=headers, password=parsed.password,
                    follow_redirects=follow_redirects,
                    connect_timeout=connect_timeout,
                    read_timeout=read_timeout,
                    write_timeout=write_timeout,
                    pool_timeout=pool_timeout,
                    client=client,
                    origin=addr.origin
                )
                if resp.status_code in RETRYABLE_STATUS_CODES:
                    msg = "{} {}:{}{} returned retryable status {}".format(
                        method, host_label, addr.port,
                        parsed.path, resp.status_code
                    )
                    logger.warning(msg)
                    errors.append(msg)
                    attempted_hosts.append("{}:{}".format(host_label, addr.port))
                    return None
                return resp

            except RETRYABLE_EXCEPTIONS as exc:
                msg = "{} {}:{}{} failed: {}".format(
                    method, host_label, addr.port, parsed.path, exc
                )
                logger.warning(msg)
                errors.append(msg)
                attempted_hosts.append("{}:{}".format(host_label, addr.port))
                return None

        if eager_resolve:
            async for addr in HttpLb.resolve_host_ports_eager(
                shuffled
            ):
                if effective_max is not None and attempts >= effective_max:
                    break
                resp = await _try_host(addr)
                if resp is not None:
                    return resp
        else:
            resolved = await HttpLb.resolve_host_ports(shuffled)
            for addr in resolved:
                if effective_max is not None and attempts >= effective_max:
                    break
                resp = await _try_host(addr)
                if resp is not None:
                    return resp

        raise HttpLbConnectionError(
            method=method,
            url=url,
            attempts=attempts,
            attempted_hosts=attempted_hosts,
            errors=errors,
        )

    @staticmethod
    async def post(
        url: str,
        body: typing.Any = None,
        content_type: typing.Optional[str] = None,
        headers: typing.Optional[typing.Dict[str, str]] = None,
        follow_redirects: bool = True,
        connect_timeout: typing.Optional[float] = None,
        read_timeout: typing.Optional[float] = None,
        write_timeout: typing.Optional[float] = None,
        pool_timeout: typing.Optional[float] = None,
        max_retries: typing.Optional[int] = None,
        eager_resolve: bool = True,
        client: typing.Optional[httpx.AsyncClient] = None,
        ) -> httpx.Response:
        """
        HTTP POST with load balancing and failover.

        Convenience wrapper around :meth:`_request_with_loadbalance`.
        See that method for full parameter documentation.
        """
        return await HttpLb._request_with_loadbalance(
            "POST", url,
            body=body, content_type=content_type, headers=headers,
            follow_redirects=follow_redirects,
            connect_timeout=connect_timeout, read_timeout=read_timeout,
            write_timeout=write_timeout, pool_timeout=pool_timeout,
            max_retries=max_retries, eager_resolve=eager_resolve,
            client=client,
        )

    @staticmethod
    async def get(
        url: str,
        headers: typing.Optional[typing.Dict[str, str]] = None,
        follow_redirects: bool = True,
        connect_timeout: typing.Optional[float] = None,
        read_timeout: typing.Optional[float] = None,
        write_timeout: typing.Optional[float] = None,
        pool_timeout: typing.Optional[float] = None,
        max_retries: typing.Optional[int] = None,
        eager_resolve: bool = True,
        client: typing.Optional[httpx.AsyncClient] = None,
        ) -> httpx.Response:
        """
        HTTP GET with load balancing and failover.

        Convenience wrapper around :meth:`_request_with_loadbalance`.
        See that method for full parameter documentation.
        """
        return await HttpLb._request_with_loadbalance(
            "GET", url,
            headers=headers,
            follow_redirects=follow_redirects,
            connect_timeout=connect_timeout, read_timeout=read_timeout,
            write_timeout=write_timeout, pool_timeout=pool_timeout,
            max_retries=max_retries, eager_resolve=eager_resolve,
            client=client,
        )


    @staticmethod
    async def put(
        url: str,
        body: typing.Any = None,
        content_type: typing.Optional[str] = None,
        headers: typing.Optional[typing.Dict[str, str]] = None,
        follow_redirects: bool = True,
        connect_timeout: typing.Optional[float] = None,
        read_timeout: typing.Optional[float] = None,
        write_timeout: typing.Optional[float] = None,
        pool_timeout: typing.Optional[float] = None,
        max_retries: typing.Optional[int] = None,
        eager_resolve: bool = True,
        client: typing.Optional[httpx.AsyncClient] = None,
        ) -> httpx.Response:
        """
        HTTP PUT with load balancing and failover.

        Convenience wrapper around :meth:`_request_with_loadbalance`.
        See that method for full parameter documentation.
        """
        return await HttpLb._request_with_loadbalance(
            "PUT", url,
            body=body, content_type=content_type, headers=headers,
            follow_redirects=follow_redirects,
            connect_timeout=connect_timeout, read_timeout=read_timeout,
            write_timeout=write_timeout, pool_timeout=pool_timeout,
            max_retries=max_retries, eager_resolve=eager_resolve,
            client=client,
        )


    @staticmethod
    async def request(
        method: str,
        url: str,
        body: typing.Any = None,
        content_type: typing.Optional[str] = None,
        headers: typing.Optional[typing.Dict[str, str]] = None,
        follow_redirects: bool = True,
        connect_timeout: typing.Optional[float] = None,
        read_timeout: typing.Optional[float] = None,
        write_timeout: typing.Optional[float] = None,
        pool_timeout: typing.Optional[float] = None,
        max_retries: typing.Optional[int] = None,
        eager_resolve: bool = True,
        client: typing.Optional[httpx.AsyncClient] = None,
        ) -> httpx.Response:
        """
        Generic HTTP request with load balancing and failover.

        Use this when the HTTP method is determined at runtime
        (e.g. from configuration or user input).

        Parameters:
          **method** (str): HTTP method (``"GET"``, ``"POST"``,
              ``"PUT"``, ``"DELETE"``, etc.).

        See :meth:`_request_with_loadbalance` for all other
        parameters.
        """
        return await HttpLb._request_with_loadbalance(
            method.upper(), url,
            body=body, content_type=content_type, headers=headers,
            follow_redirects=follow_redirects,
            connect_timeout=connect_timeout, read_timeout=read_timeout,
            write_timeout=write_timeout, pool_timeout=pool_timeout,
            max_retries=max_retries, eager_resolve=eager_resolve,
            client=client,
        )

