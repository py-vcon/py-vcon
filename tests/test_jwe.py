""" Unit tests for JWE encrypted vCon """

import pytest
import vcon
import vcon.security
import json
import typing

CA_CERT = "certs/fake_ca_root.crt"
DIVISION_CERT = "certs/fake_div.crt"
DIVISION_PRIVATE_KEY = "certs/fake_div.key"
GROUP_CERT = "certs/fake_grp.crt"
GROUP_PRIVATE_KEY = "certs/fake_grp.key"

call_data = {
      "epoch" : "1652552179",
      "destination" : "2117",
      "source" : "+19144345359",
      "rfc2822" : "Sat, 14 May 2022 18:16:19 -0000",
      "rfc3339" : "2022-05-14T18:16:19.000+00:00",
      "file_extension" : "WAV",
      "duration" : 94.84,
      "channels" : 1
}

@pytest.fixture(scope="function")
def empty_vcon() -> vcon.Vcon:
  """ construct vCon with no data """
  vCon = vcon.Vcon()
  return(vCon)

@pytest.fixture(scope="function")
def two_party_tel_vcon(empty_vcon : vcon.Vcon) -> vcon.Vcon:
  """ construct vCon with two tel URL """
  vCon = empty_vcon
  first_party = vCon.set_party_parameter("tel", call_data['source'])
  second_party = vCon.set_party_parameter("tel", call_data['destination'])
  vCon.set_uuid("vcon.dev")
  return(vCon)

import jose.jwe
import jwcrypto.jwe
import secrets
import cryptography.x509

def test_encrypt(two_party_tel_vcon : vcon.Vcon) -> None:
  plaintext = two_party_tel_vcon.dumps()

  symmetric_key = jose.utils.base64url_encode(secrets.token_bytes(nbytes=int(256/8))).decode("utf-8")
  print("sym key: {}".format(symmetric_key))

  content_key = {}
  content_key["kty"] = "oct"
  content_key["k"] = symmetric_key
  content_key["enc"] = "A256GCM"

  jwe_content_token = jose.jwe.encrypt(plaintext,
    jose.utils.base64url_decode(bytes(content_key["k"], "utf-8")),
    encryption=content_key['enc'],
    algorithm="dir",
    cty="application/vcon").decode('utf-8')
  print("token: {}".format(jwe_content_token))
  (protected, content_encrypted_key, iv, cyphertext, authentication_tag) = jwe_content_token.split('.')
  print("protected: {}".format(jose.utils.base64url_decode(bytes(protected, 'utf-8'))))
  print("content enc key: {}".format(content_encrypted_key))


  decrypt_content_token = ".".join([protected, "", iv, cyphertext, authentication_tag])
  print("decrypt token: {}".format(decrypt_content_token))

  decrypted_plaintext = jose.jwe.decrypt(decrypt_content_token,
    jose.utils.base64url_decode(bytes(content_key["k"], "utf-8")))
  assert(decrypted_plaintext.decode("utf-8") == plaintext)


def test_x5c_encrypt(two_party_tel_vcon : vcon.Vcon) -> None:
  plaintext = two_party_tel_vcon.dumps()

  encryption_key = vcon.security.build_encryption_jwk_from_pem_file(DIVISION_CERT)
  assert(not encryption_key.has_private)

  # both of these work
  #encryption = "A256GCM"
  encryption = "A256CBC-HS512"

  jwe = jwcrypto.jwe.JWE(plaintext.encode("utf-8"),
    protected = json.dumps({"alg": "RSA-OAEP", "enc": encryption}))
  jwe.add_recipient(encryption_key)
  jwe_compact_token = jwe.serialize(compact = True)

  (header, decryption_key) = vcon.security.build_signing_jwk_from_pem_files(DIVISION_PRIVATE_KEY, [DIVISION_CERT])
  assert(decryption_key.has_private)
  assert(decryption_key.thumbprint() == encryption_key.thumbprint())

  jwe_decrypted = jwcrypto.jwe.JWE()
  jwe_decrypted.deserialize(jwe_compact_token, decryption_key)
  plaintext_decrypted = jwe_decrypted.payload.decode('utf-8')

  assert(plaintext == plaintext_decrypted)


def test_encrypt_decrypt(two_party_tel_vcon : vcon.Vcon) -> None:
  try:
    two_party_tel_vcon.encrypt(DIVISION_CERT)
    raise Exception("Should have thrown an exception as this vcon was not yet signed")

  except vcon.InvalidVconState as not_signed_error:
    if(not_signed_error.args[0].find("should") != -1):
      raise not_signed_error

  two_party_tel_vcon.sign(GROUP_PRIVATE_KEY, [GROUP_CERT, DIVISION_CERT, CA_CERT])

  two_party_tel_vcon.encrypt(DIVISION_CERT)

  encrypted_serialized_vcon = two_party_tel_vcon.dumps()
  #print(encrypted_serialized_vcon)

  assert(two_party_tel_vcon._state == vcon.VconStates.ENCRYPTED)

  reconstituted_vcon = vcon.Vcon()
  reconstituted_vcon.loads(encrypted_serialized_vcon)
  assert(reconstituted_vcon._state == vcon.VconStates.ENCRYPTED)

  try:
    reconstituted_vcon.verify([CA_CERT])
    raise Exception("Should have thrown an exception as this vcon is still encrypted")

  except vcon.InvalidVconState as encrypted_not_signed_error:
    if(encrypted_not_signed_error.args[0].find("should") != -1):
      raise encrypted_not_signed_error

  reconstituted_vcon.decrypt(DIVISION_PRIVATE_KEY, DIVISION_CERT)
  assert(reconstituted_vcon._state == vcon.VconStates.UNVERIFIED)

  reconstituted_vcon.verify([CA_CERT])
  assert(reconstituted_vcon._state == vcon.VconStates.VERIFIED)

  assert(reconstituted_vcon.parties[0]['tel'] == call_data['source'])
  assert(reconstituted_vcon.parties[1]['tel'] == call_data['destination'])


def test_pem_strings_encrypt_decrypt(two_party_tel_vcon : vcon.Vcon) -> None:
  division_cert_string = vcon.security.load_string_from_file(DIVISION_CERT)
  division_private_key_string = vcon.security.load_string_from_file(DIVISION_PRIVATE_KEY)
  group_private_key_string = vcon.security.load_string_from_file(GROUP_PRIVATE_KEY)
  group_cert_string = vcon.security.load_string_from_file(GROUP_CERT)
  ca_cert_string = vcon.security.load_string_from_file(CA_CERT)

  try:
    two_party_tel_vcon.encrypt(division_cert_string)
    raise Exception("Should have thrown an exception as this vcon was not yet signed")

  except vcon.InvalidVconState as not_signed_error:
    if(not_signed_error.args[0].find("should") != -1):
      raise not_signed_error

  two_party_tel_vcon.sign(group_private_key_string, [group_cert_string, division_cert_string, ca_cert_string])

  two_party_tel_vcon.encrypt(division_cert_string)

  encrypted_serialized_vcon = two_party_tel_vcon.dumps()
  #print(encrypted_serialized_vcon)

  assert(two_party_tel_vcon._state == vcon.VconStates.ENCRYPTED)

  reconstituted_vcon = vcon.Vcon()
  reconstituted_vcon.loads(encrypted_serialized_vcon)
  assert(reconstituted_vcon._state == vcon.VconStates.ENCRYPTED)

  try:
    reconstituted_vcon.verify([ca_cert_string])
    raise Exception("Should have thrown an exception as this vcon is still encrypted")

  except vcon.InvalidVconState as encrypted_not_signed_error:
    if(encrypted_not_signed_error.args[0].find("should") != -1):
      raise encrypted_not_signed_error

  reconstituted_vcon.decrypt(division_private_key_string, division_cert_string)
  assert(reconstituted_vcon._state == vcon.VconStates.UNVERIFIED)

  reconstituted_vcon.verify([ca_cert_string])
  assert(reconstituted_vcon._state == vcon.VconStates.VERIFIED)

  assert(reconstituted_vcon.parties[0]['tel'] == call_data['source'])
  assert(reconstituted_vcon.parties[1]['tel'] == call_data['destination'])


def test_encrypt_decrypt_serialization(two_party_tel_vcon : vcon.Vcon) -> None:

  two_party_tel_vcon.sign(GROUP_PRIVATE_KEY, [GROUP_CERT, DIVISION_CERT, CA_CERT])
  assert(two_party_tel_vcon._state == vcon.VconStates.SIGNED)

  signed_serialized_vcon = two_party_tel_vcon.dumps()

  # Verify the signed vcon can be deserialized and verified
  reconstituted_signed_vcon = vcon.Vcon()
  reconstituted_signed_vcon.loads(signed_serialized_vcon)
  assert(reconstituted_signed_vcon._state == vcon.VconStates.UNVERIFIED)
  reconstituted_signed_vcon.verify([CA_CERT])
  assert(reconstituted_signed_vcon._state == vcon.VconStates.VERIFIED)

  assert(reconstituted_signed_vcon.parties[0]['tel'] == call_data['source'])
  assert(reconstituted_signed_vcon.parties[1]['tel'] == call_data['destination'])

  two_party_tel_vcon.encrypt(DIVISION_CERT)
  assert(two_party_tel_vcon._state == vcon.VconStates.ENCRYPTED)

  serialized_encrypted_vcon = two_party_tel_vcon.dumps()

  reconstituted_encrypted_vcon = vcon.Vcon()
  reconstituted_encrypted_vcon.loads(serialized_encrypted_vcon)
  assert(reconstituted_encrypted_vcon._state == vcon.VconStates.ENCRYPTED)

  reconstituted_encrypted_vcon.decrypt(DIVISION_PRIVATE_KEY, DIVISION_CERT)
  assert(reconstituted_encrypted_vcon._state == vcon.VconStates.UNVERIFIED)

  serialized_decrypted_signed_vcon = reconstituted_encrypted_vcon.dumps()

  reconstituted_decrypted_signed_vcon = vcon.Vcon()
  reconstituted_decrypted_signed_vcon.loads(serialized_decrypted_signed_vcon)
  assert(reconstituted_decrypted_signed_vcon._state == vcon.VconStates.UNVERIFIED)

  reconstituted_decrypted_signed_vcon.verify([CA_CERT])
  assert(reconstituted_decrypted_signed_vcon._state == vcon.VconStates.VERIFIED)

  assert(reconstituted_decrypted_signed_vcon.parties[0]['tel'] == call_data['source'])
  assert(reconstituted_decrypted_signed_vcon.parties[1]['tel'] == call_data['destination'])

  reconstituted_encrypted_vcon.verify([CA_CERT])
  assert(reconstituted_encrypted_vcon._state == vcon.VconStates.VERIFIED)

  assert(reconstituted_encrypted_vcon.parties[0]['tel'] == call_data['source'])
  assert(reconstituted_encrypted_vcon.parties[1]['tel'] == call_data['destination'])

  unsigned_decrypted_verified_vcon = reconstituted_encrypted_vcon.dumps(signed=False)

  reconstituted_unsigned_vcon = vcon.Vcon()
  reconstituted_unsigned_vcon.loads(unsigned_decrypted_verified_vcon)
  assert(reconstituted_unsigned_vcon._state == vcon.VconStates.UNSIGNED)

  assert(reconstituted_unsigned_vcon.parties[0]['tel'] == call_data['source'])
  assert(reconstituted_unsigned_vcon.parties[1]['tel'] == call_data['destination'])
