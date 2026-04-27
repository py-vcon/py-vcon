# Copyright (C) 2023-2026 SIPez LLC.  All rights reserved.
""" Build script for python-vcon-core package for pypi """
import io
import os
import shutil
import sys
import typing
import setuptools
import setuptools.command.sdist


class sdist_with_setup(setuptools.command.sdist.sdist):
    print("DEBUG: sdist_with_setup class defined", file=sys.stderr)
    def run(self):
        print("DEBUG: run called", file=sys.stderr)
        super().run()
        # Find the generated tarball and replace setup.py inside it
        import tarfile
        import tempfile
        import glob
        tarballs = glob.glob("dist/python-vcon-core-*.tar.gz")
        for tarball in tarballs:
            print("DEBUG: patching tarball: {}".format(tarball), file=sys.stderr)
            # read tarball, replace setup.py, write back
            with tarfile.open(tarball, "r:gz") as tar_in:
                members = tar_in.getmembers()
                files = {}
                for member in members:
                    f = tar_in.extractfile(member)
                    files[member] = f.read() if f else None
            with tarfile.open(tarball, "w:gz") as tar_out:
                for member, content in files.items():
                    if member.name.endswith("/setup.py"):
                        print("DEBUG: replacing setup.py in {}".format(member.name), file=sys.stderr)
                        with open("setup_core.py", "rb") as f:
                            content = f.read()
                        member.size = len(content)
                    if content is not None:
                        tar_out.addfile(member, io.BytesIO(content))
                    else:
                        tar_out.addfile(member)


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


REQUIRES = get_requirements("vcon/docker_dev/pip_package_list_core.txt", REQUIRES)
print("vcon-core package dependencies: {}".format(REQUIRES), file=sys.stderr)


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
  name='python-vcon-core',
  version=__version__,
  description='vCon conversational data container core package (no ML/API filter plugin dependencies)',
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
    ("vcon", ["vcon/docker_dev/pip_package_list_core.txt"])],
  python_requires=">=3.8",
  tests_require=['pytest', 'pytest-asyncio', 'pytest-dependency', "pytest_httpserver"],
  install_requires=REQUIRES,
  scripts=['vcon/bin/vcon'],
  zip_safe=False)

