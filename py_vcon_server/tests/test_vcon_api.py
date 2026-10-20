# Copyright (C) 2023-2026 SIPez LLC.  All rights reserved.
# Copyright (C) 2026 SIP Spectrum, Inc.  All rights reserved.
import asyncio
import pytest
import pytest_asyncio
import py_vcon_server
import py_vcon_server.certs
import py_vcon_server.db
import py_vcon_server.settings
import vcon
import fastapi.testclient
from common_setup import UUID, make_2_party_tel_vcon

@pytest.mark.asyncio
async def test_set_get_delete(make_2_party_tel_vcon: vcon.Vcon):
  vCon = make_2_party_tel_vcon

  with fastapi.testclient.TestClient(py_vcon_server.restapi) as client:

    set_response = client.post("/vcon", json=vCon.dumpd())
    assert(set_response.status_code == 204)

    get_response = client.get(
      "/vcon/{}".format(UUID),
      headers={"accept": "application/json"},
      )
    assert(get_response.status_code == 200)
    vcon_dict = get_response.json()
    assert(vcon_dict["parties"][0]["tel"] == "1234")
    assert(vcon_dict["parties"][1]["tel"] == "5678")
    got_vcon = vcon.Vcon()
    got_vcon.loads(get_response.text)
    assert(got_vcon.parties[0]["tel"] == "1234")
    assert(got_vcon.parties[1]["tel"] == "5678")

    delete_response = client.delete("/vcon/{}".format(UUID))
    assert(delete_response.status_code == 204)
    assert(delete_response.text == "")

    get2_response = client.get(
      "/vcon/{}".format(UUID),
      headers={"accept": "application/json"},
      )
    assert(get2_response.status_code == 404)

@pytest.mark.asyncio
async def test_jq(make_2_party_tel_vcon: vcon.Vcon):
  vCon = make_2_party_tel_vcon

  with fastapi.testclient.TestClient(py_vcon_server.restapi) as client:

    set_response = client.post("/vcon", json=vCon.dumpd())
    assert(set_response.status_code == 204)

    query = {}
    query["jq_transform"] = ".parties[]"

    jq_response = client.get(
      "/vcon/{}/jq".format(UUID),
      params=query,
      headers={"accept": "application/json"},
      )

    assert(jq_response.status_code == 200)
    query_list = jq_response.json()
    assert(len(query_list) == 2)
    assert(query_list[0]["tel"] == "1234")
    assert(query_list[1]["tel"] == "5678")

@pytest.mark.asyncio
async def test_jsonpath(make_2_party_tel_vcon: vcon.Vcon):
  vCon = make_2_party_tel_vcon

  with fastapi.testclient.TestClient(py_vcon_server.restapi) as client:

    set_response = client.post("/vcon", json=vCon.dumpd())
    assert(set_response.status_code == 204)

    query = {}
    query["path_string"] = "$.parties"

    jsonpath_response = client.get(
      "/vcon/{}/jsonpath".format(UUID),
      params=query,
      headers={"accept": "application/json"},
      )

    assert(jsonpath_response.status_code == 200)
    query_list = jsonpath_response.json()[0]
    assert(len(query_list) == 2)
    assert(query_list[0]["tel"] == "1234")
    assert(query_list[1]["tel"] == "5678")

CA_CERT = "../certs/fake_ca_root.crt"
OTHER_CA_CERT = "../certs/fake_ca2_root.crt"
GROUP_CERT = "../certs/fake_grp.crt"
GROUP_PRIVATE_KEY = "../certs/fake_grp.key"
DIVISION_CERT = "../certs/fake_div.crt"


def sign_vcon(vCon: vcon.Vcon) -> vcon.Vcon:
  """ Sign the vCon with the test certificate chain """
  vCon.sign(GROUP_PRIVATE_KEY, [GROUP_CERT, DIVISION_CERT, CA_CERT])
  return(vCon)


class SignedVconStorage():
  """
  Storage stub returning a signed vCon, so the entry points can be tested
  without a storage back end (and without POST /vcon, which takes the UUID from
  the document: the JWS form does not carry one).
  """
  def __init__(self, vcon_dict: dict):
    self.vcon_dict = vcon_dict

  async def get(self, vcon_uuid: str) -> vcon.Vcon:
    if(vcon_uuid != UUID):
      raise py_vcon_server.db.VconNotFound("vCon not found for UUID: {}".format(vcon_uuid))
    a_vcon = vcon.Vcon()
    a_vcon.loadd(self.vcon_dict)
    return(a_vcon)

  async def shutdown(self) -> None:
    """ called when the app shuts down """


@pytest.mark.asyncio
async def test_jq_signed_vcon(make_2_party_tel_vcon: vcon.Vcon, monkeypatch):
  """ A signed vCon is verified with the configured CA certs, then queried """
  vCon = sign_vcon(make_2_party_tel_vcon)

  with fastapi.testclient.TestClient(py_vcon_server.restapi) as client:
    monkeypatch.setattr(py_vcon_server.db, "VCON_STORAGE", SignedVconStorage(vCon.dumpd()))

    # no CA certificates configured: the content cannot be read
    monkeypatch.setattr(py_vcon_server.settings, "VCON_CA_CERT_PEMS", [])
    response = client.get("/vcon/{}/jq".format(UUID), params = {"jq_transform": ".parties[]"})
    assert(response.status_code == 422), response.text
    assert("VCON_CA_CERT_PEMS" in response.json()["detail"])

    # the wrong CA: verification fails and says so
    monkeypatch.setattr(py_vcon_server.settings, "VCON_CA_CERT_PEMS", [OTHER_CA_CERT])
    response = client.get("/vcon/{}/jq".format(UUID), params = {"jq_transform": ".parties[]"})
    assert(response.status_code == 422), response.text
    assert("could not be verified" in response.json()["detail"])

    # the signing CA: the vCon content is queried, not the JWS envelope
    monkeypatch.setattr(py_vcon_server.settings, "VCON_CA_CERT_PEMS", [CA_CERT])
    response = client.get("/vcon/{}/jq".format(UUID), params = {"jq_transform": ".parties[]"})
    assert(response.status_code == 200), response.text
    query_list = response.json()
    assert(len(query_list) == 2)
    assert(query_list[0]["tel"] == "1234")
    assert(query_list[1]["tel"] == "5678")


@pytest.mark.asyncio
async def test_jsonpath_signed_vcon(make_2_party_tel_vcon: vcon.Vcon, monkeypatch):
  """ A signed vCon is verified with the configured CA certs, then queried with JSONPath """
  vCon = sign_vcon(make_2_party_tel_vcon)

  with fastapi.testclient.TestClient(py_vcon_server.restapi) as client:
    monkeypatch.setattr(py_vcon_server.db, "VCON_STORAGE", SignedVconStorage(vCon.dumpd()))

    # no CA certificates configured: the content cannot be read
    monkeypatch.setattr(py_vcon_server.settings, "VCON_CA_CERT_PEMS", [])
    response = client.get("/vcon/{}/jsonpath".format(UUID), params = {"path_string": "$.parties"})
    assert(response.status_code == 422), response.text
    assert("VCON_CA_CERT_PEMS" in response.json()["detail"])

    # the signing CA: the vCon content is queried, not the JWS envelope
    monkeypatch.setattr(py_vcon_server.settings, "VCON_CA_CERT_PEMS", [CA_CERT])
    response = client.get("/vcon/{}/jsonpath".format(UUID), params = {"path_string": "$.parties"})
    assert(response.status_code == 200), response.text
    query_list = response.json()[0]
    assert(len(query_list) == 2)
    assert(query_list[0]["tel"] == "1234")
    assert(query_list[1]["tel"] == "5678")


@pytest.mark.asyncio
async def test_jsonpath_rfc9535(make_2_party_tel_vcon: vcon.Vcon):
  """ JSONPath is RFC 9535, evaluated the same whatever the storage back end """
  vCon = make_2_party_tel_vcon

  with fastapi.testclient.TestClient(py_vcon_server.restapi) as client:
    assert(client.post("/vcon", json = vCon.dumpd()).status_code == 204)
    try:
      def query(path):
        return(client.get("/vcon/{}/jsonpath".format(UUID), params = {"path_string": path}))

      # filter selector, in both the RFC 9535 and the parenthesized form
      assert(query('$.parties[?@.tel == "5678"].tel').json() == ["5678"])
      assert(query('$.parties[?(@.tel == "1234")].tel').json() == ["1234"])
      # descendant segment
      assert(query("$..tel").json() == ["1234", "5678"])
      # nothing selected is an empty list, not an error
      assert(query("$.no_such_member").json() == [])

      # a query that is not valid RFC 9535 (here SQL/JSON path syntax) is a client error
      response = query('$.parties[*] ? (@.tel == "1234")')
      assert(response.status_code == 422), response.text
      assert("RFC 9535" in response.json()["detail"])
    finally:
      client.delete("/vcon/{}".format(UUID))


def test_trusted_ca_pems(tmp_path, monkeypatch):
  """ Entries may be a file, a directory of certificates, or an inline PEM """
  cert_dir = tmp_path / "ca-certs"
  cert_dir.mkdir()
  pem = "-----BEGIN CERTIFICATE-----{}{}{}-----END CERTIFICATE-----{}"
  (cert_dir / "root.crt").write_text(pem.format(chr(10), "root", chr(10), chr(10)))
  (cert_dir / "partner.pem").write_text(pem.format(chr(10), "partner", chr(10), chr(10)))
  (cert_dir / "notes.txt").write_text("not a certificate")

  monkeypatch.setattr(py_vcon_server.settings, "VCON_CA_CERT_PEMS", [str(cert_dir)])
  pems = py_vcon_server.certs.trusted_ca_pems()
  assert(len(pems) == 2)
  assert(pems[0].endswith("partner.pem"))
  assert(pems[1].endswith("root.crt"))

  inline = pem.format(chr(10), "inline", chr(10), "")
  monkeypatch.setattr(py_vcon_server.settings, "VCON_CA_CERT_PEMS", [CA_CERT, inline])
  assert(py_vcon_server.certs.trusted_ca_pems() == [CA_CERT, inline])

  monkeypatch.setattr(py_vcon_server.settings, "VCON_CA_CERT_PEMS", [])
  assert(py_vcon_server.certs.trusted_ca_pems() == [])


@pytest.mark.asyncio
async def test_post_vcon_missing_uuid():
  """POST /vcon with no UUID set should return validation error"""
  with fastapi.testclient.TestClient(py_vcon_server.restapi) as client:

    # Build a minimal vCon dict with the uuid removed
    vcon_dict = {
      "vcon": "0.0.2",
      "uuid": "",
      "created_at": "2024-03-06T20:07:43.000+00:00",
      "parties": [],
      "dialog": [],
      "analysis": [],
      "attachments": []
    }

    post_response = client.post("/vcon", json=vcon_dict)
    assert(post_response.status_code == 422)


@pytest.mark.asyncio
async def test_get_vcon_not_found():
  """GET /vcon/{uuid} for a non-existent UUID should return 404"""
  with fastapi.testclient.TestClient(py_vcon_server.restapi) as client:

    get_response = client.get(
      "/vcon/00000000-0000-0000-0000-000000000000",
      headers={"accept": "application/json"},
    )
    assert(get_response.status_code == 404)


@pytest.mark.asyncio
async def test_jq_not_found(make_2_party_tel_vcon: vcon.Vcon):
  """GET /vcon/{uuid}/jq for a non-existent UUID should return 500"""
  with fastapi.testclient.TestClient(py_vcon_server.restapi) as client:

    query = {"jq_transform": ".uuid"}
    jq_response = client.get(
      "/vcon/00000000-0000-0000-0000-000000000000/jq",
      params=query,
      headers={"accept": "application/json"},
    )
    assert(jq_response.status_code == 404)


@pytest.mark.asyncio
async def test_jsonpath_not_found():
  """GET /vcon/{uuid}/jsonpath for a non-existent UUID should return 500"""
  with fastapi.testclient.TestClient(py_vcon_server.restapi) as client:

    query = {"path_string": "$.uuid"}
    jsonpath_response = client.get(
      "/vcon/00000000-0000-0000-0000-000000000000/jsonpath",
      params=query,
      headers={"accept": "application/json"},
    )
    assert(jsonpath_response.status_code == 404)


@pytest.mark.asyncio
async def test_delete_vcon_not_found():
  """DELETE /vcon/{uuid} for a non-existent UUID should return 204 (idempotent)"""
  with fastapi.testclient.TestClient(py_vcon_server.restapi) as client:

    delete_response = client.delete("/vcon/00000000-0000-0000-0000-000000000000")
    # Redis delete of non-existent key is not an error
    assert(delete_response.status_code == 204)

