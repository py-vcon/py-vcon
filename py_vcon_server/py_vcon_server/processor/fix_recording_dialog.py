# Copyright (C) 2023-2025 SIPez LLC.  All rights reserved.
""" Registration for the fix recording dialog **VconProcessor** """
import py_vcon_server.processor
import py_vcon_server.processor.builtin.fix_recording_dialog

init_options = py_vcon_server.processor.builtin.fix_recording_dialog.FixRecordingDialogInitOptions()

py_vcon_server.processor.VconProcessorRegistry.register(
      init_options,
      "fix_recording_dialog",
      "py_vcon_server.processor.builtin.fix_recording_dialog",
      "FixRecordingDialog"
      )

