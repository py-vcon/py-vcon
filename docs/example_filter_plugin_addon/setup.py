# Copyright (C) 2023-2025 SIPez LLC.  All rights reserved.
""" Build script for vcon filter_plugin addon package for pypi """
import typing
import setuptools

REQUIRES: typing.List[str] = ["python-vcon"]

__version__ = "0.0.1"

setuptools.setup(
  name='vcon.filter_plugins_addons.my-filter',
  version=__version__,
  description='my custom filter_plugin package',
  author='Dan Petrie',
  author_email='dan.vcon@sipez.com',
  license='MIT',
  packages=[
      # namespace dir/sub-package where add on filter_plugins will appear
      'vcon',
      'vcon.filter_plugins_addons',
      'vcon.filter_plugins_addons.my_filter_impl',
    ],

  python_requires=">=3.8",
  install_requires = REQUIRES,
  scripts=[],
  zip_safe=False)

