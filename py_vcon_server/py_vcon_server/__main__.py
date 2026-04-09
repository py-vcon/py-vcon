# Copyright (C) 2023-2026 SIPez LLC.  All rights reserved.
import urllib
import uvicorn
from . import settings, logging_utils
from py_vcon_server import Server

logger = logging_utils.init_logger(__name__)


def main():
  "Start the vCon server with Uvicorn (multi-worker capable)"
  url_parser = urllib.parse.urlparse(settings.REST_URL)
  host_ip = url_parser.hostname
  port_num = url_parser.port
  logger.info("vCon server binding to host: {} port: {} with {} workers".format(
      host_ip, port_num, settings.NUM_RESTAPI_WORKERS))

  config = uvicorn.Config(
      "py_vcon_server:restapi",
      workers=settings.NUM_RESTAPI_WORKERS,
      loop="asyncio",
      host=host_ip,
      port=port_num,
  )
  server = Server(config=config)

  if settings.NUM_RESTAPI_WORKERS > 1:
    from uvicorn.supervisors import Multiprocess
    sock = config.bind_socket()
    Multiprocess(config, target=server.run, sockets=[sock]).run()
  else:
    server.run()


if __name__ == "__main__":
  main()

