""" Build script for vcon core package for pypi """
# import os
import sys
import typing
import setuptools

REQUIRES: typing.List[str] = []

# print("CWD: {}".format(os.getcwd()), file=sys.stderr)
# print("files in CWD: {}".format(os.listdir(os.getcwd())), file=sys.stderr)


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


REQUIRES = get_requirements("vcon/docker_dev/pip_package_list.txt", REQUIRES)
print("vcon package dependencies: {}".format(REQUIRES), file = sys.stderr)


def get_version() -> str:
  """ 
  This is kind of a PITA, but the build system barfs when we import vcon here
  as depenencies are not installed yet in the vritual environment that the 
  build creates.  Therefore we cannot access version directly from vcon/__init__.py.
  So I have hacked this means of parcing the version value rather than
  de-normalizing it and having it set in multiple places.
  """
  with open("vcon/__init__.py", "rt") as core_file:
    line = core_file.readline()
    while line:
      if(line.startswith("__version__")):
        variable, equals, version = line.split()
        assert(variable == "__version__")
        assert(equals == "=")
        version = version.strip('"')
        version_double = float(version)
        assert(version_double >= 0.01)
        assert(version_double < 10.0)
        break

      line = core_file.readline()

  return(version)


__version__ = get_version()

setuptools.setup(
  name='python-vcon',
  version=__version__,
  # version="0.1",
  description='vCon conversational data container manipulation package',
  url='http://github.com/py-vcon/py-vcon',
  author='Dan Petrie',
  author_email='dan.vcon@sipez.com',
  license='MIT',
  packages=['vcon', 'vcon.filter_plugins', 'vcon.filter_plugins.impl'],
  data_files=[
    ("vcon", ["vcon/docker_dev/pip_package_list.txt"])],
  python_requires=">=3.7",
  tests_require=['pytest', 'pytest-asyncio', 'pytest-dependency', "pytest_httpserver"],
  install_requires = REQUIRES,
  scripts=['vcon/bin/vcon'],
  # entry_points={
  #   'console_scripts': [
  #     'vcon = vcon:cli:main',
  #     ]
  #   }
  zip_safe=False)

