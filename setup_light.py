# Copyright (C) 2023-2026 SIPez LLC.  All rights reserved.
""" Build script for python-vcon-light package for pypi """
import os
import shutil
import sys
import typing
import setuptools
import setuptools.command.sdist


class sdist_with_setup(setuptools.command.sdist.sdist):
    def make_release_tree(self, base_dir, files):
        super().make_release_tree(base_dir, files)
        # Break any hard link and replace setup.py with the correct one
        # so that pip runs the correct setup when installing from tarball
        target = os.path.join(base_dir, "setup.py")
        if os.path.exists(target):
            os.unlink(target)
        shutil.copy("setup_light.py", target)

REQUIRES: typing.List[str] = []


def get_requirements(
    filename: str,
    requires: typing.List[str]
  ) -> typing.List[str]:
  """ get pip package names from text file """
  with open(filename, "rt") as core_file:
    line = core_file.readline()
    while line:
      line = line.strip()
      if(len(line) > 0 and line[0] != '#'):
        requires.append(line)
      line = core_file.readline()
  return(requires)


REQUIRES = get_requirements("vcon/docker_dev/pip_package_list_light.txt", REQUIRES)
print("vcon-light package dependencies: {}".format(REQUIRES), file=sys.stderr)


def get_version() -> str:
  """ Parse version from vcon/__init__.py without importing it """
  with open("vcon/__init__.py", "rt") as core_file:
    line = core_file.readline()
    while line:
      if(line.startswith("__version__")):
        variable, equals, version = line.split()
        assert(variable == "__version__")
        assert(equals == "=")
        version = version.strip('"')
        versions = version.split(".")
        assert(int(versions[0]) >= 0)
        assert(int(versions[0]) < 10)
        assert(2 <= len(versions) <= 3)
        assert(int(versions[1]) >= 0)
        if(len(versions) == 3):
          assert(int(versions[2]) >= 0)
        break
      line = core_file.readline()
  return(version)


__version__ = get_version()

setuptools.setup(
  name='python-vcon-light',
  version=__version__,
  description='vCon conversational data container package with light API-based filter plugins (Deepgram, OpenAI)',
  url='http://github.com/py-vcon/py-vcon',
  author='Dan Petrie',
  author_email='dan.vcon@sipez.com',
  license='MIT',
  packages=[
      'vcon',
      'vcon.filter_plugins',
      'vcon.filter_plugins.impl',
      'vcon.filter_plugins_addons',
    ],
  data_files=[
    ("vcon", ["vcon/docker_dev/pip_package_list_light.txt"])],
  python_requires=">=3.8",
  tests_require=['pytest', 'pytest-asyncio', 'pytest-dependency', "pytest_httpserver"],
  install_requires=[
      "python-vcon-core >= {}".format(__version__)
    ] + REQUIRES,
  scripts=['vcon/bin/vcon'],
  zip_safe=False)

