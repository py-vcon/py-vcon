# Copyright (C) 2023-2025 SIPez LLC.  All rights reserved.
""" Registration for the Whisper OpenAI transcription **VconProcessor** with base model size """
import py_vcon_server.processor
import py_vcon_server.processor.builtin.whisper

base_model_init_options = py_vcon_server.processor.builtin.whisper.WhisperInitOptions(model_size = "base")

py_vcon_server.processor.VconProcessorRegistry.register(
      base_model_init_options,
      "whisper_base",
      "py_vcon_server.processor.builtin.whisper",
      "Whisper"
      )

