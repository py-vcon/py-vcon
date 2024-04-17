# Copyright (C) 2023-2024 SIPez LLC.  All rights reserved.
""" bad implementations of **VconProcessor** for testing """

import py_vcon_server.processor


class ImplementsNothing(py_vcon_server.processor.VconProcessor):
  """ Attempt to hide abstract class """


class ImplementsMinimalInitOnly(py_vcon_server.processor.VconProcessor):
  """ Attempt to hide abstract class """
  def __init__(self, options: py_vcon_server.processor.VconProcessorInitOptions):
    super().__init__(
      None,
      None,
      "0.0.0",
      options,
      py_vcon_server.processor.VconProcessorOptions,
      True
      )


