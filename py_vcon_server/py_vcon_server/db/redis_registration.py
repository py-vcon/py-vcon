# Copyright (C) 2023-2024 SIPez LLC.  All rights reserved.
""" Register redis as a VconStorage interface """

import py_vcon_server.db
import py_vcon_server.db.redis
import py_vcon_server.db.redis.redis_mgr

# Register the redis implementation of Vcon Storage Interface
py_vcon_server.db.VconStorage.register("redis", py_vcon_server.db.redis.RedisVconStorage)

