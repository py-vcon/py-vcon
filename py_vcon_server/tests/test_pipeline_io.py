# Copyright (C) 2023-2024 SIPez LLC.  All rights reserved.
import asyncio
import pytest
import pytest_asyncio
import importlib
import copy
import py_vcon_server.processor
from common_setup import UUID, make_2_party_tel_vcon
import vcon


