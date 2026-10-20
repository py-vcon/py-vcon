# Copyright (C) 2026 SIPez LLC.  All rights reserved.
# Redis Sentinel test cluster - single container running one master,
# one replica and three sentinels on non-standard ports to avoid
# conflicting with any existing Redis/Sentinel instances on the host.
#
# Master:    port 6399
# Replica:   port 6400
# Sentinel1: port 26399
# Sentinel2: port 26400
# Sentinel3: port 26401
#
# Built on redis/redis-stack-server so JSON path operations work,
# matching the redis-stack-server used in CI for the main test suite.
FROM redis/redis-stack-server:latest

COPY entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

CMD ["/entrypoint.sh"]

