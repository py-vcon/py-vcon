# Copyright (C) 2026 SIP Spectrum, Inc.  All rights reserved.
"""
Trusted Certificate Authority certificates for the server, and verification of
signed vCons read from storage.

The certificates come from the VCON_CA_CERT_PEMS setting.  Directories are
expanded when they are used rather than at startup, so a certificate added to
or rotated in a mounted directory takes effect without restarting the server.
"""

import os
import glob
import typing
import vcon
import py_vcon_server.settings
import py_vcon_server.logging_utils

logger = py_vcon_server.logging_utils.init_logger(__name__)

# file name patterns read from a directory given in VCON_CA_CERT_PEMS
CERT_FILE_PATTERNS = ["*.pem", "*.crt"]

PEM_PREFIX = "-----BEGIN"


class VconNotReadable(Exception):
  """
  The content of a stored vCon cannot be read: it is signed and could not be
  verified, or it is encrypted.
  """


def trusted_ca_pems() -> typing.List[str]:
  """
  The trusted CA certificates, as Vcon.verify takes them: a list whose entries
  are file names or PEM strings.  A directory in the setting contributes each
  of its certificate files.

  Returns: list of file names and PEM strings, empty if none are configured
  """
  pems = []
  for entry in py_vcon_server.settings.VCON_CA_CERT_PEMS:
    if(entry.startswith(PEM_PREFIX)):
      pems.append(entry)
    elif(os.path.isdir(entry)):
      for pattern in CERT_FILE_PATTERNS:
        pems.extend(sorted(glob.glob(os.path.join(entry, pattern))))
    else:
      pems.append(entry)

  return(pems)


def verify_for_read(a_vcon: vcon.Vcon) -> bool:
  """
  Make the content of a vCon read from storage readable.

  An unsigned vCon is already readable.  A signed one is verified with the
  trusted CA certificates, which is what allows its payload to be read.  An
  encrypted one cannot be read without the recipient's private key, which the
  server does not hold.

  Parameters:
    **a_vcon** (Vcon): vCon as read from VconStorage

  Returns: True if the vCon was signed and has been verified, False if it was
    not signed

  Raises: VconNotReadable if it is encrypted, or signed and not verifiable
  """
  state = a_vcon.state

  if(state in [vcon.VconStates.UNSIGNED, vcon.VconStates.SIGNED, vcon.VconStates.VERIFIED]):
    return(state == vcon.VconStates.VERIFIED)

  if(state in [vcon.VconStates.ENCRYPTED, vcon.VconStates.DECRYPTED]):
    raise VconNotReadable(
        "vCon UUID: {} is encrypted, its content cannot be read without decrypting it"
        " (the decrypt processor, with the recipient's private key)".format(a_vcon.uuid)
      )

  # UNVERIFIED: signed, read from storage, not yet verified
  ca_pems = trusted_ca_pems()
  if(len(ca_pems) == 0):
    raise VconNotReadable(
        "vCon UUID: {} is signed and no trusted CA certificates are configured, so its"
        " content cannot be read.  Set VCON_CA_CERT_PEMS to the CA certificate(s) that"
        " signed it.".format(a_vcon.uuid)
      )

  try:
    a_vcon.verify(ca_pems)
  except Exception as e:
    # some verification failures raise with no message, so name the exception
    reason = "{}: {}".format(type(e).__name__, e) if str(e) else type(e).__name__
    logger.info("vCon UUID: {} signature verification failed: {}".format(a_vcon.uuid, reason))
    raise VconNotReadable(
        "vCon UUID: {} is signed and its signature could not be verified with the"
        " configured CA certificates: {}".format(a_vcon.uuid, reason)
      ) from e

  return(True)
