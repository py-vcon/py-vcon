import os
import pytest
import pytest_asyncio
import json
import fastapi.testclient
import py_vcon_server

@pytest.mark.asyncio
async def test_get_docs_html():
  with fastapi.testclient.TestClient(py_vcon_server.restapi) as client:
    get_response = client.get(
      "/docs"
      #headers={"accept": "application/json"},
      )
    assert(get_response.status_code == 200)
    content_html = get_response.content.decode("utf-8")

    # Fix css and js linkes
    #content_html = content_html.replace("https://cdn.jsdelivr.net/npm/swagger-ui-dist@4/", "")

    # Fix openai.json linkes
    content_html = content_html.replace("/openapi.json", "openapi.json")

    # Fix absolute path server linkes
    # TODO content_html = content_html.replace("/openapi.json", "openapi.json")

    # when running the unit tests outside the source tree docs 
    # does not exist.
    if(not os.path.isdir("docs")):
      os.mkdir("docs")
    with open("docs/swagger.html", "wt") as html_file:
      html_file.write(content_html)

    get_response = client.get(
      "/openapi.json"
      #headers={"accept": "application/json"},
      )
    assert(get_response.status_code == 200)
    swagger_dict = get_response.json()

    with open("docs/openapi.json", "wt") as swagger_file:
      # Write out in formated json so that diffs are more readable
      json.dump(swagger_dict, swagger_file, indent = 2)

