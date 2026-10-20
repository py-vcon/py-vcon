# Copyright (C) 2023-2026 SIPez LLC.  All rights reserved.
""" VconProcessor module whose top-level code raises, for testing
VconProcessor load failure handling when the failure happens during
importlib.import_module() (not during class instantiation by the registry).

Mirrors the production openai_chat_completion failure mode:
py_vcon_server/processor/builtin/openai.py calls makeInitOptions() at
module top level, which transitively instantiates the underlying
FilterPlugin and raises openai.OpenAIError.

Here the VconProcessor's own __init__ raises, and the module top level
instantiates the class -- so importlib.import_module() unwinds with the
RuntimeError, exactly matching how the openai exception unwinds through
load_module().
"""

import py_vcon_server.processor


class TopLevelRaisingProcessor(py_vcon_server.processor.VconProcessor):
  """ VconProcessor whose __init__ unconditionally raises """
  def __init__(self, init_options):
    raise RuntimeError("simulated VconProcessor init failure at module top level")

  async def process(self, processor_input, options):
    raise NotImplementedError


# Top-level instantiation -- mirrors makeInitOptions() in builtin/openai.py.
# This causes importlib.import_module() to unwind with the RuntimeError
# raised by TopLevelRaisingProcessor.__init__.
_dummy = TopLevelRaisingProcessor(py_vcon_server.processor.VconProcessorInitOptions())

