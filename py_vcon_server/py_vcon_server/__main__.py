# Copyright (C) 2023-2025 SIPez LLC.  All rights reserved.
import asyncio
import urllib
import uvicorn
from . import restapi, settings, logging_utils

logger = logging_utils.init_logger(__name__)


class Server(uvicorn.Server):
    def handle_exit(self, sig: int, frame) -> None:
        return super().handle_exit(sig, frame)

async def main():
    "the enabled APIs"
    url_parser = urllib.parse.urlparse(settings.REST_URL)
    host_ip = url_parser.hostname
    port_num = url_parser.port
    logger.info("vCon server binding to host: {} port: {} with {} workers".format(
      host_ip, port_num, settings.NUM_RESTAPI_WORKERS))

    server = Server(config=uvicorn.Config(
        app=restapi,
        workers=settings.NUM_RESTAPI_WORKERS,
        loop="asyncio",
        host=host_ip,
        port=port_num,
        reload=True))

    api_task = asyncio.create_task(server.serve())

    await asyncio.wait([api_task])

asyncio.run(main())

