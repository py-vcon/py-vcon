#!/bin/bash
# Copyright (C) 2026 SIPez LLC.  All rights reserved.
# Start the Redis Sentinel test cluster in a Docker container.
#
# The cluster runs on non-standard ports to avoid conflicting with
# any existing Redis or Sentinel instances on the host:
#   Redis master:  6399
#   Redis replica: 6400
#   Sentinel 1:    26399
#   Sentinel 2:    26400
#   Sentinel 3:    26401
#
# Prerequisites - these kernel parameters must be set on the HOST
# (not inside the container - containers cannot set them):
#
#   sudo sysctl -w vm.overcommit_memory=1
#   sudo sysctl -w net.core.somaxconn=65535
#
# To persist across reboots:
#   echo 'vm.overcommit_memory=1' | sudo tee -a /etc/sysctl.conf
#   echo 'net.core.somaxconn=65535' | sudo tee -a /etc/sysctl.conf
#
# Usage:
#   bash scripts/start_sentinel.sh
#
# To run sentinel tests:
#   export VCON_STORAGE_URL=sentinel://localhost:26399,localhost:26400,localhost:26401/mymaster?db=0
#   pytest tests/test_redis_sentinel.py -v

set -e

CONTAINER_NAME=py_vcon_sentinel_test
IMAGE_NAME=py_vcon_sentinel:test
SENTINEL_PORT=26399
WAIT_SECONDS=10

# Check sysctl values - warn but do not abort, as some environments
# have these set correctly without reporting the expected value
OVERCOMMIT=$(cat /proc/sys/vm/overcommit_memory 2>/dev/null || echo "unknown")
SOMAXCONN=$(cat /proc/sys/net/core/somaxconn 2>/dev/null || echo "unknown")

if [ "${OVERCOMMIT}" != "1" ]; then
  echo "WARNING: vm.overcommit_memory=${OVERCOMMIT} (expected 1)"
  echo "         Redis may log warnings or fail to fork during failover."
  echo "         Fix with: sudo sysctl -w vm.overcommit_memory=1"
fi

if [ "${SOMAXCONN}" != "65535" ]; then
  echo "WARNING: net.core.somaxconn=${SOMAXCONN} (expected 65535)"
  echo "         Redis listen backlog may be clamped under high connection load."
  echo "         Fix with: sudo sysctl -w net.core.somaxconn=65535"
fi

# Remove any leftover container from a previous run
if docker ps -a --format '{{.Names}}' | grep -q "^${CONTAINER_NAME}$"; then
  echo "Removing existing container ${CONTAINER_NAME}..."
  docker rm -f ${CONTAINER_NAME}
fi

echo "Building sentinel image..."
docker build -t ${IMAGE_NAME} docker/sentinel/

echo "Starting sentinel cluster container..."
docker run -d \
  --name ${CONTAINER_NAME} \
  --network host \
  --security-opt seccomp=unconfined \
  --security-opt apparmor=unconfined \
  --cap-add SYS_PTRACE --cap-add SYS_NICE --cap-add SYS_ADMIN \
  --ulimit nproc=65535 --ulimit nofile=65535:65535 \
  --pids-limit=-1 \
  ${IMAGE_NAME}

echo "Waiting up to ${WAIT_SECONDS}s for sentinel to be ready..."
for i in $(seq 1 ${WAIT_SECONDS}); do
  if python3 -c "
import socket
s = socket.create_connection(('localhost', ${SENTINEL_PORT}), timeout=1.0)
s.close()
" 2>/dev/null; then
    echo "Sentinel ready after ${i}s"
    echo ""
    echo "Run sentinel tests with:"
    echo "  export VCON_STORAGE_URL=sentinel://localhost:26399,localhost:26400,localhost:26401/mymaster?db=0"
    echo "  pytest tests/test_redis_sentinel.py -v"
    exit 0
  fi
  echo "Waiting... (${i}/${WAIT_SECONDS})"
  sleep 1
done

echo "ERROR: Sentinel not ready after ${WAIT_SECONDS}s"
echo "Container logs:"
docker logs ${CONTAINER_NAME}
exit 1

import sys, redis
try:
  r = redis.Redis(host='localhost', port=${SENTINEL_PORT})
  masters = r.execute_command('SENTINEL', 'masters')
  print('ok')
except Exception as e:
  print('err: {}'.format(e))
" 2>/dev/null)
  if [ "${RESULT}" = "ok" ]; then
    echo "Sentinel ready after ${i}s"
    echo ""
    echo "Run sentinel tests with:"
    echo "  export VCON_STORAGE_URL=sentinel://localhost:26399,localhost:26400,localhost:26401/mymaster?db=0"
    echo "  pytest tests/test_redis_sentinel.py -v"
    exit 0
  fi
  sleep 1
done

echo "ERROR: Sentinel not ready after ${WAIT_SECONDS}s"
echo "Container logs:"
docker logs ${CONTAINER_NAME}
exit 1

