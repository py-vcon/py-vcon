# Copyright (C) 2023-2025 SIPez LLC.  All rights reserved.
""" Unit test for fix_recording_dialog plugin """
import vcon
import pytest

def test_add_transfer_dialog():
  xfer_vcon = vcon.Vcon()
  transferee = 0
  transferor = 1
  transfer_target = 2
  original_dialog = 3
  consultative_dialog = 4
  target_dialog = 5

  xfer_index = xfer_vcon.add_transfer_dialog(
      transferee,
      transferor,
      transfer_target,
      original_dialog,
      target_dialog,
      consultative_dialog
    )

  assert(xfer_index == 0)
  assert(xfer_vcon.dialog[0]["type"] == "transfer")
  assert(xfer_vcon.dialog[0]["transferee"] == transferee)
  assert(xfer_vcon.dialog[0]["transferor"] == transferor)
  assert(xfer_vcon.dialog[0]["transfer_target"] == transfer_target)
  assert(xfer_vcon.dialog[0]["original"] == original_dialog)
  assert(xfer_vcon.dialog[0]["consultation"] == consultative_dialog)
  assert(xfer_vcon.dialog[0]["target_dialog"] == target_dialog)

  xfer_index2 = xfer_vcon.add_transfer_dialog(
      transferee,
      transferor,
      transfer_target,
      original_dialog,
      None,
      None
    )

  assert(xfer_index2 == 1)
  assert(xfer_vcon.dialog[1]["type"] == "transfer")
  assert(xfer_vcon.dialog[1]["transferee"] == transferee)
  assert(xfer_vcon.dialog[1]["transferor"] == transferor)
  assert(xfer_vcon.dialog[1]["transfer_target"] == transfer_target)
  assert(xfer_vcon.dialog[1]["original"] == original_dialog)
  assert("consultation" not in xfer_vcon.dialog[1])
  assert("target_dialog" not in xfer_vcon.dialog[1])


