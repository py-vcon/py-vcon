# Copyright (C) 2023-2024 SIPez LLC.  All rights reserved.
""" Build script for vcon server package for pypi """
import os
import sys
import typing
import setuptools
import shutil

REQUIRES: typing.List[str] = ["py-vcon-server"]


print("CWD: {}".format(os.getcwd()))


__version__ = "0.0.1"

found_packages = setuptools.find_namespace_packages(where=".")
print("Found packages: {}".format(found_packages))

setuptools.setup(
  name='py_vcon_server.processor_addons.my-vcon-processor',
  version=__version__,
  description='server for vCon conversational data container manipulation package',
  author='Dan Petrie',
  author_email='dan.vcon@sipez.com',
  license='MIT',
  #namespace_packages=[
  #  'py_vcon_server',
  #  'py_vcon_server.processor_addons'
  #],
  #packages=found_packages,
  packages=[
      # dir/sub-package where add on VconProcessors will appear to be installed
      # They will not really be installed here, but the package manager will make
      # it appear so.  Use the following in VconProcessor plugin packages:
      'py_vcon_server',
      'py_vcon_server.processor_addons',
      'py_vcon_server.processor_addons.my_proc_impl',
    ],

  python_requires=">=3.8",
  install_requires = REQUIRES,
  scripts=[],
  zip_safe=False)

