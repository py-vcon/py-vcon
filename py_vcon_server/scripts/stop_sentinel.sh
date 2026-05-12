#!/bin/bash
# Copyright (C) 2026 SIPez LLC.  All rights reserved.
# Stop and remove the Redis Sentinel test cluster container.

CONTAINER_NAME=py_vcon_sentinel_test

if docker ps -a --format '{{.Names}}' | grep -q "^${CONTAINER_NAME}$"; then
  echo "Stopping and removing ${CONTAINER_NAME}..."
  docker rm -f ${CONTAINER_NAME}
  echo "Done."
else
  echo "Container ${CONTAINER_NAME} not found, nothing to do."
fi

