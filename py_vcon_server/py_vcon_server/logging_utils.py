# Copyright (C) 2023-2025 SIPez LLC.  All rights reserved.
import os
import sys
import logging
import logging.config
import pythonjsonlogger.jsonlogger

def init_logger(name : str) -> logging.Logger:
  logger = logging.getLogger(name)

  log_config_filename = "./logging.conf"
  if(os.path.isfile(log_config_filename)):
    logging.config.fileConfig(log_config_filename)
    #print("got logging config", file=sys.stderr)
  else:
    logger.setLevel(logging.DEBUG)

    handler = logging.StreamHandler(sys.stdout)
    handler.setLevel(logging.DEBUG)
    # see python LogRecord attributes for more attribute names
    formatter = pythonjsonlogger.jsonlogger.JsonFormatter(
        "%(timestamp)s %(process)d %(levelname)s %(message)s %(pathname)s %(module)s %(lineno)d",
         timestamp = True
      )
    handler.setFormatter(formatter)
    logger.addHandler(handler)

  return(logger)

