#!/bin/bash
# Copyright (C) 2023-2026 SIPez LLC.  All rights reserved.
# Entrypoint for the Redis Sentinel test cluster container.
# Starts one Redis master, one replica and three Sentinel processes,
# all on non-standard ports, then waits for any child to exit.
#
# Ports:
#   Master:    6399
#   Replica:   6400
#   Sentinel1: 26399
#   Sentinel2: 26400
#   Sentinel3: 26401

set -e

MASTER_PORT=6399
REPLICA_PORT=6400
SENTINEL_PORTS="26399 26400 26401"
MASTER_NAME=mymaster
SENTINEL_QUORUM=2
DOWN_AFTER_MS=5000
FAILOVER_TIMEOUT_MS=10000
PARALLEL_SYNCS=1
REJSON_MODULE=/opt/redis-stack/lib/rejson.so

CONFIG_DIR=/tmp/redis-sentinel-test

mkdir -p ${CONFIG_DIR}

echo "--- Starting Redis master on port ${MASTER_PORT}"
redis-server \
  --port ${MASTER_PORT} \
  --daemonize no \
  --loglevel notice \
  --loadmodule ${REJSON_MODULE} \
  &
MASTER_PID=$!

# Give master a moment to bind before replica tries to connect
sleep 1

echo "--- Starting Redis replica on port ${REPLICA_PORT}"
redis-server \
  --port ${REPLICA_PORT} \
  --daemonize no \
  --loglevel notice \
  --replicaof 127.0.0.1 ${MASTER_PORT} \
  --loadmodule ${REJSON_MODULE} \
  &
REPLICA_PID=$!

# Generate sentinel config files and start each sentinel
for PORT in ${SENTINEL_PORTS}; do
  CFG=${CONFIG_DIR}/sentinel-${PORT}.conf
  cat > ${CFG} << EOF
port ${PORT}
sentinel monitor ${MASTER_NAME} 127.0.0.1 ${MASTER_PORT} ${SENTINEL_QUORUM}
sentinel down-after-milliseconds ${MASTER_NAME} ${DOWN_AFTER_MS}
sentinel failover-timeout ${MASTER_NAME} ${FAILOVER_TIMEOUT_MS}
sentinel parallel-syncs ${MASTER_NAME} ${PARALLEL_SYNCS}
EOF
  echo "--- Starting Sentinel on port ${PORT}"
  redis-sentinel ${CFG} &
done

echo "--- All processes started"
echo "    Master   PID: ${MASTER_PID}  port: ${MASTER_PORT}"
echo "    Replica  PID: ${REPLICA_PID}  port: ${REPLICA_PORT}"
echo "    Sentinels on ports: ${SENTINEL_PORTS}"

# Wait for any child process to exit -- if any Redis process dies
# unexpectedly the container will stop, making failures visible.
wait -n 2>/dev/null || wait
echo "--- A child process exited, container stopping"

