""" Build script for vcon server package for pypi """
import os
import sys
import typing
import setuptools
import shutil

REQUIRES: typing.List[str] = ["python-vcon"]

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

print("CWD: {}".format(os.getcwd()))
if(os.path.exists("../vcon/docker_dev/pip_server_requirements.txt")):
  print("copying ../vcon/docker_dev/pip_server_requirements.txt")
  shutil.copyfile("../vcon/docker_dev/pip_server_requirements.txt", "pip_server_requirements.txt")
else:
  print("using cached pip_server_requirements.txt exists")
#REQUIRES = get_requirements("vcon/docker_dev/pip_package_list.txt", REQUIRES)
REQUIRES = get_requirements("pip_server_requirements.txt", REQUIRES)
print("vcon server package dependencies: {}".format(REQUIRES), file = sys.stderr)


def get_version() -> str:
  """ 
  This is kind of a PITA, but the build system barfs when we import vcon here
  as depenencies are not installed yet in the vritual environment that the 
  build creates.  Therefore we cannot access version directly from vcon/__init__.py.
  So I have hacked this means of parcing the version value rather than
  de-normalizing it and having it set in multiple places.
  """
  with open("py_vcon_server/__init__.py", "rt") as core_file:
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
  name='py-vcon-server',
  version=__version__,
  # version="0.1",
  description='server for vCon conversational data container manipulation package',
  url='http://github.com/py-vcon/py-vcon/py_vcon_server',
  author='Dan Petrie',
  author_email='dan.vcon@sipez.com',
  license='MIT',
  packages=[
      'py_vcon_server',
      'py_vcon_server.db',
      'py_vcon_server.db.redis',
      'py_vcon_server.processor',
      'py_vcon_server.processor.builtin',
      'py_vcon_server.states',
      'py_vcon_server.queue',
    ],
  data_files=[
      ("py_vcon_server", ["pip_server_requirements.txt"]),
      ("tests", ["tests/hello.wav", "tests/hello.m4a"]),
    ],
  python_requires=">=3.7",
  tests_require=['pytest', 'pytest-asyncio', 'pytest-dependency', "pytest_httpserver"],
  install_requires = REQUIRES,
  #scripts=['vcon/bin/vcon'],
  scripts=[],
  # entry_points={
  #   'console_scripts': [
  #     'vcon = vcon:cli:main',
  #     ]
  #   }
  zip_safe=False)

