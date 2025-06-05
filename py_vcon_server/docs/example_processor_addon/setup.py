# Copyright (C) 2023-2025 SIPez LLC.  All rights reserved.
""" Build script for vcon server package for pypi """
import typing
import setuptools

REQUIRES: typing.List[str] = ["py-vcon-server"]


__version__ = "0.0.1"

setuptools.setup(
  name='py_vcon_server.processor_addons.my-vcon',
  version=__version__,
  description='server for vCon conversational data container manipulation package',
  author='Dan Petrie',
  author_email='dan.vcon@sipez.com',
  license='MIT',
  packages=[
      # namespace dir/sub-package where addon VconProcessors will appear to be installed
      'py_vcon_server',
      'py_vcon_server.processor_addons',
      'py_vcon_server.processor_addons.my_proc_impl',
    ],

  python_requires=">=3.8",
  install_requires = REQUIRES,
  scripts=[],
  zip_safe=False)

