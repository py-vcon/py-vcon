""" Common setup and components for the RESTful APIs """
import pydantic
import fastapi

class HttpErrorResponseBody(pydantic.BaseModel):
  """ Error return type object for APIs """
  detail: str

ERROR_RESPONSES = {
  404: {
    "model" : HttpErrorResponseBody
    },
  500: {
    "model" : HttpErrorResponseBody
    }
}


class NotFoundResponse(fastapi.responses.JSONResponse):
  """ Helper class to handle 404 Not Found cases """
  def __init__(self, detail: str):
    super().__init__(status_code = 404,
      content = {"detail": detail})

class InternalErrorResponse(fastapi.responses.JSONResponse):
  """ Helper class to handle 500 internal server error case """
  def __init__(self, exception: Exception):
    super().__init__(status_code = 500,
      content = {"detail": str(exception)})


