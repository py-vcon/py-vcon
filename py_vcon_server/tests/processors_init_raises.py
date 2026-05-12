# Copyright (C) 2023-2026 SIPez LLC.  All rights reserved.
""" VconProcessor module that imports cleanly but whose VconProcessor
__init__ raises, for testing registration failure handling when the
failure happens during VconProcessorRegistration's instantiation of
the processor class (not during module import).
"""

import py_vcon_server.processor


class InitRaisingProcessor(py_vcon_server.processor.VconProcessor):
  """ VconProcessor that raises in __init__ when instantiated by the registry """
  def __init__(self, init_options):
    raise RuntimeError("simulated VconProcessor init failure")

  async def process(self, processor_input, options):
    raise NotImplementedError

