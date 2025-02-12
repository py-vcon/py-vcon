# Copyright (C) 2023-2025 SIPez LLC.  All rights reserved.
import pydantic

pydantic_major, pydantic_minor, pydantic_release = pydantic.__version__.split(".")

if(pydantic_major == '1'):
  ValidationErrorType = pydantic.error_wrappers.ValidationError
  IntParseError = "type_error.integer"
  FloatParseError = "type_error.float"
  FieldInfo = pydantic.fields.ModelField
  ALLOW = pydantic.Extra.allow
  SET_ALLOW = {'extra': ALLOW}

  def set_field_default(cls, field_name: str, new_default):
    cls.__fields__[field_name].default = new_default


  def get_field_items(pydantic_type):
    return(pydantic_type.__fields__.items())


  def get_model_schema(pydantic_type):
    return(pydantic_type.schema())


  def get_fields_set(model):
    return(model.__fields_set__)


  def get_dict(model, exclude_none=True):
    return(model.dict(exclude_none = exclude_none))


elif(pydantic_major == '2'):
  import pydantic_core
  import pydantic.fields
  ValidationErrorType = pydantic_core._pydantic_core.ValidationError
  IntParseError = "int_parsing"
  FloatParseError = "float_parsing"
  FieldInfo = pydantic.fields.FieldInfo
  ALLOW = 'allow'
  SET_ALLOW = {'extra': ALLOW}
  #SET_ALLOW = {'json_schema_extra': ALLOW}

  def set_field_default(cls, field_name: str, new_default):
    cls.model_fields[field_name].default = new_default


  def get_field_items(pydantic_type):
    return(pydantic_type.model_fields.items())


  def get_model_schema(pydantic_type):
    return(pydantic_type.model_json_schema())


  def get_fields_set(model):
    return(model.model_fields_set)


  def get_dict(model, exclude_none=True):
    return(model.model_dump(exclude_none = exclude_none))


else:
  raise Exception("unsupported major version of pydantic: {} ({})".format(pydantic_major, pydantic.__version__))

