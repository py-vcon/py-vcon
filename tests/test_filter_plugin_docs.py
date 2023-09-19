#!/usr/bin/python3


import inspect
import typing
import importlib
import pkgutil
import pydantic
import vcon.filter_plugins
import vcon.filter_plugins.impl.whisper

PYDANTIC_FIELD_ATTRIBUTES = ["name", "type", "title", "description", "example", "examples", "default"]

PAGE_TEMPLATE = """
# Filter Plugins

## Table of Contents
 + [Introduction](#introduction)
 + [Filter Plugin Classes](filter-plugin-classes)
{plugins_toc}
 + [Filter Plugin Initialization Options Classes](filter-plugin-initialization-options-classes)
{init_options_toc}
 + [Filter Plugin Options Classes](filter-plugin-options-classes)
{options_toc}

## Introduction

TBD

# Filter Plugin Classes

{plugins}

# Filter Plugin Initialization Options Classes

{init_options}

# Filter Plugin Options Classes

{options}

"""

CLASS_TEMPLATE = """
## {class_name}
 - {class_title}

{class_description}

#### Fields:
"""

FIELD_TEMPLATE = """
##### {name} ({type})
{title}
{description}

example{example}

default: {default}
"""

def clean_doc_indentation(doc: str) -> str:
  lines = doc.splitlines()
  last_line = lines[-1]
  index = 0
  while(index < len(last_line) and last_line[index] == " "):
    index += 1

  clean_lines = []
  for line in lines:
    clean_lines.append(line[index:])

  return("\n".join(clean_lines))


def make_section_link(target_title: str, label: str) -> str:
  anchor = "#" + target_title.lower().replace(".", "").replace(" ", "-")
  link = "[{}]({})".format(label, anchor)

  return(link)

def doc_pydantic(pydantic_type: typing.Type[pydantic.BaseModel]) -> str:
  """ Generate markdown for a pydantic BaseModel derived class """
  assert(issubclass(pydantic_type, pydantic.BaseModel))
  class_data = {}
  class_schema = pydantic_type.schema()
  class_data["class_name"] = pydantic_type.__module__ + "." + pydantic_type.__name__
  class_data["class_title"] = class_schema.get("title", "")
  #doc = "**{}** - {}\n".format(pydantic_type.__name__,
  #  class_title if class_title != pydantic_type.__name__ else ""
  #  )
  class_data["class_description"] = class_schema.get("description", "<no class doc>")
  assert(class_data["class_description"] is not None)
  #doc += class_desc + "\n\n"
  #doc += "**Fields**:\n"
  doc = CLASS_TEMPLATE.format(**class_data)

  fields_added = 0
  for _, field in pydantic_type.__fields__.items():
    fields_added += 1
    assert(isinstance(field, pydantic.fields.ModelField))
    field_data = {}
    for attribute in PYDANTIC_FIELD_ATTRIBUTES:
      if(hasattr(field, attribute)):
        value = getattr(field, attribute)
      elif(hasattr(field.field_info, attribute)):
        value = getattr(field.field_info, attribute)
      else:
        value = None
      if(value is None):
        value = field.field_info.extra.get(attribute, None)
      #if(value is not None):
      field_data[attribute] = value

    if(not hasattr(field.annotation, "__name__")):
      field_type = str(field.annotation)
      print("Field: {} in class: {} module: {} does not have a type hint set. annotation type: {} {}".format(
        field_data["name"],
        pydantic_type.__name__,
        pydantic_type.__module__,
        type(field.annotation),
        field.annotation
        ))
    else:
      field_type = field.annotation.__name__
    field_data["type"] = field_type
    if(field_type == "str" and
      field_data.get("default", None) is not None):
      # put quotes around default if this is type str
      field_data["default"] = '"{}"'.format(field_data["default"])

    # Tweak examples
    if("examples" in field_data and
      field_data["examples"] is not None and
      field_data["examples"] != ""
      ):
      field_data["example"] = "s: " + str(field_data["examples"])
    elif("example" in field_data and
      field_data["example"] is not None
      ):
      field_data["example"] = ": " + field_data["example"]
    else:
      field_data["example"] = ": "

    doc += FIELD_TEMPLATE.format(**field_data)

  if(fields_added == 0):
    doc += "None\n"
  return(doc)

PLUGIN_TEMPLATE = """
## {name}
{description}

**Methods**:

### \_\_init__
\_\_init__{__init___signature}
{__init___description}

**{__init___option_name}** - {__init___option_type}

### filter{filter_signature}

{filter_description}

**{filter_option_name}** - {filter_option_type}

### \_\_del__{__del___signature}

{__del___description}

"""


def doc_plugin(plugin_class: typing.Type[vcon.filter_plugins.FilterPlugin],
  init_options,
  options
  ) -> str:
  plugin_data = {}
  plugin_data["name"] = plugin_class.__module__ + "." + plugin_class.__name__
  plugin_data["description"] = plugin_class.__doc__


  method_dict = {}
  for name, cls in inspect.getmembers(plugin_class, predicate = inspect.isfunction):
    method_dict[name] = cls

  # class_dict = {}
  # for name, cls in inspect.getmembers(plugin_class.__module__, predicate = inspect.isclass):
  #   print("adding class_dict[{}] : {}".format(name, cls))
  #   class_dict[name] = cls

  doc_methods = ["__init__", "filter", "__del__"]
  for name in doc_methods:
    cls = method_dict[name]
    sig = inspect.signature(cls)
    # print("setting: " + name + "_signature")
    plugin_data[name + "_signature"] = str(sig)
    plugin_data[name + "_description"] = cls.__doc__
    # print(dir(sig))
    # print("{}{}".format(name, str(sig)))
    arg_keys = list(sig.parameters)
    if(name == "filter"):
      option_index = 2
      expected_options_base_class = vcon.filter_plugins.FilterPluginOptions
      type_set = options
    elif(name == "__init__"):
      option_index = 1
      expected_options_base_class = vcon.filter_plugins.FilterPluginInitOptions
      type_set = init_options
    else:
      option_index = -1

    if(option_index >= 0):
      option_arg_name = arg_keys[option_index]
      plugin_data[name + "_option_name"] = option_arg_name
      option_arg_type = sig.parameters[option_arg_name].annotation
      # Sometimes the annoation, is the string type name instead of the type
      # This is a know python issue related to the use of :
      #   from __future__ import annotations
      # It is not consistant and appears to be some sort of timing or async issue
      if(not hasattr(option_arg_type, "__module__")):
        module_name = plugin_class.__module__
        module = globals().get(module_name, None)
        if(module is None):
          # try to load the module
          module = importlib.import_module(module_name)
        option_arg_type = getattr(module, option_arg_type)
        # assert(issubclass(option_arg_type, vcon.filter_plugins.FilterPluginInitOptions))
        #arg_type = option_arg_type
      else:
        module_name = option_arg_type.__module__
      arg_type = option_arg_type.__name__
      if(not issubclass(option_arg_type, expected_options_base_class)):
        raise Exception("argument: {} in method: {} of FilterPlugin: {} in module: {} does not derived from: {}".format(
          option_arg_name,
          name,
          plugin_class,
          plugin_class.__module__,
          expected_options_base_class.__name__
          ))

      # make this a anchor link
      fullname = module_name + "." + arg_type
      plugin_data[name + "_option_type"] = make_section_link(fullname, fullname)
      # print("{}: {}".format(option_arg_name, option_arg_type))
      type_set.add(option_arg_type)
    #elif(name == "__init__"):
    elif(False):
      option_arg_name = arg_keys[1]
      plugin_data[name + "_option_name"] = option_arg_name
      option_arg_type = sig.parameters[option_arg_name].annotation
      # may need to use typing.get_type_hints(class) instead
      memb = getattr(cls, name)
      # print("memb type: {} {} mod: {}".format(type(memb), memb, cls.__module__))
      arg_dict = typing.get_type_hints(memb)
      # print("hints {}: {}".format(name, arg_dict))
      # print("hints {}: {}".format(name, arg_dict[name]))
      # print("sig params: {}".format(sig.parameters))
      # print("sig params: {} {}".format(option_arg_name, sig.parameters[option_arg_name]))
      # print("sig params dir: {}".format(dir(sig.parameters[option_arg_name])))
      # print("sig params type: {}".format(type(sig.parameters[option_arg_name])))
      # print("sig params name: {} type: {}".format(sig.parameters[option_arg_name], type(sig.parameters[option_arg_name])))
      # print("sig params annotation: {}".format(sig.parameters[option_arg_name].annotation))
      # print("sig params annotation: {}".format(sig.parameters[option_arg_name].annotation))
      # print("sig params annotation dir: {}".format(dir(sig.parameters[option_arg_name].annotation)))
      # print("sig params annotation type: {}".format(type(sig.parameters[option_arg_name].annotation)))

      # Sometimes the annoation, is the string type name instead of the type
      # This is a know python issue related to the use of :
      #   from __future__ import annotations
      # It is not consistant and appears to be some sort of timing or async issue
      if(not hasattr(option_arg_type, "__module__")):
        module_name = plugin_class.__module__
        # TODO: try
        module = globals().get(module_name, None)
        if(module is None):
          # try to load the module
          module = importlib.import_module(module_name)
        option_arg_type = getattr(module, option_arg_type)
        # assert(issubclass(option_arg_type, vcon.filter_plugins.FilterPluginInitOptions))
        #arg_type = option_arg_type
      else:
        module_name = option_arg_type.__module__
      arg_type = option_arg_type.__name__
      assert(issubclass(option_arg_type, vcon.filter_plugins.FilterPluginInitOptions))
      # make this a anchor link
      fullname = module_name + "." + arg_type
      plugin_data[name + "_option_type"] = make_section_link(fullname, fullname)
      #print("{}: {}".format(option_arg_name, option_arg_type))
      init_options.add(option_arg_type)

    plugin_data[name + "_description"] = clean_doc_indentation(cls.__doc__)

  return(PLUGIN_TEMPLATE.format(**plugin_data))

def get_module_plugin_info(
  mod,
  plugins: set,
  init_options: set,
  options) -> typing.Tuple[set, set, set]:

  for name, cls in mod.__dict__.items():
    if(isinstance(cls, type)):
      #print("found: {}".format(name))

      if(issubclass(cls, vcon.filter_plugins.FilterPlugin)):
        plugins.add(cls)

      if(issubclass(cls, vcon.filter_plugins.FilterPluginInitOptions)):
        init_options.add(cls)

      if(issubclass(cls, vcon.filter_plugins.FilterPluginOptions)):
        options.add(cls)


  return(plugins, init_options, options)

def sort_types(type_set: typing.Set[typing.Type], head: typing.Type) -> typing.List[typing.Type]:
  sorted_list = sorted(type_set.copy(), key = lambda cls: cls.__name__)
  sorted_list.remove(head)
  sorted_list.insert(0, head)

  return(sorted_list)


def main() -> str:
  plugins: typing.Set[typing.Type[vcon.filter_plugins.FilterPlugin]] = set()
  plugins.add(vcon.filter_plugins.FilterPlugin)
  init_options: typing.Set[typing.Type[vcon.filter_plugins.FilterPluginInitOptions]] = set()
  init_options.add(vcon.filter_plugins.FilterPluginInitOptions)
  options: typing.Set[typing.Type[vcon.filter_plugins.FilterPluginOptions]] = set()
  options.add(vcon.filter_plugins.FilterPluginOptions)

  mods = [
  #  vcon.filter_plugins.impl.whisper
  ]
  # get the list of builtin FilterPlugin modules
  path = [vcon.filter_plugins.__path__[0] + "/impl"]
  print("mod path: {}".format(
    path
    ))
  for finder, module_name, is_package in pkgutil.iter_modules(
    path,
    vcon.filter_plugins.__name__ + ".impl."
    ):
    mods.append(importlib.import_module(module_name))

  for module in mods:
    print("inspecting module: {}".format(module))
    plugins, init_options, options = get_module_plugin_info(
      module,
      plugins,
      init_options,
      options)
    print("plugins: {}".format(plugins))
    print("init_options: {}".format(init_options))
    print("options: {}".format(options))

  page_data = {}

  plugin_doc = ""
  plugin_toc = ""
  sorted_plugins = sort_types(plugins, vcon.filter_plugins.FilterPlugin)
  for plugin_class in sorted_plugins:
    plugin_doc += doc_plugin(plugin_class, init_options, options)
    fullname = plugin_class.__module__ + "." + plugin_class.__name__
    if(plugin_toc != ""):
      plugin_toc += "\n"
    plugin_toc += "   - " + make_section_link(fullname, fullname)
  page_data["plugins"] = plugin_doc
  page_data["plugins_toc"] = plugin_toc

  init_options_doc = ""
  init_options_toc = ""
  sorted_init_options = sort_types(init_options, vcon.filter_plugins.FilterPluginInitOptions)
  for init_option in sorted_init_options:
    init_options_doc += doc_pydantic(init_option)
    fullname = init_option.__module__ + "." + init_option.__name__
    if(init_options_toc != ""):
      init_options_toc += "\n"
    init_options_toc += "   - " + make_section_link(fullname, fullname)
  page_data["init_options"] = init_options_doc
  page_data["init_options_toc"] = init_options_toc

  options_doc = ""
  options_toc = ""
  sorted_options = sort_types(options, vcon.filter_plugins.FilterPluginOptions)
  for option in sorted_options:
    options_doc += doc_pydantic(option)
    fullname = option.__module__ + "." + option.__name__
    if(options_toc != ""):
      options_toc += "\n"
    options_toc += "   - " + make_section_link(fullname, fullname)
  page_data["options"] = options_doc
  page_data["options_toc"] = options_toc

  print("plugins: {}".format(plugins))
  print("init_options: {}".format(init_options))
  print("options: {}".format(options))

  return(PAGE_TEMPLATE.format(**page_data))

def test_filter_plugin_readme_doc():
  page_doc = main()
  with open("vcon/filter_plugins/README.md", "w") as readme_file:
    readme_file.write(page_doc)

if(__name__ == '__main__'):

  page_doc = main()
  with open("vcon/filter_plugins/README.md", "w") as readme_file:
    readme_file.write(page_doc)

