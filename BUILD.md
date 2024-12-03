# Build Instructions

  + [Building Vcon package](#building-vcon-package)
  + [Building the Vcon Server package](py_vcon_server/BUILD.md)

## Building Vcon package

Make sure python build and twine packages are installed:

    pip3 install --upgrade build twine

Create a clean clone of the branch that you want to build as any files in your development area may get accidently included in the vcon package:

    git clone https://github.com/py-vcon/py-vcon.git
    git checkout [xxxxx_commit_SHA]

Update the package __version__ number in vcon/vcon/__init__.py

Be sure to clean out the dist directory:

    rm dist/*

In the vcon directory (root containing setup.py and vcon sub-directory):

    python3 -m build

This creates sub-directory dist containing (x.x.x in the names below represents the version number):

  * python_vcon-x.x.x-py3-none-any.whl
  * python_vcon-x.x.x.tar.gz

Test your package files on a clean VM or Docker container following [these instructions](README.md#testing-the-vcon-package) after installing the vCon package:

    pip3 install dist/python_vcon-<x.x.x..tar.gz

Push the package install files up to the pypi repo.

For the test repo:

 1) Go to https://test.pypi.org/manage/account/
 2) Create an API token
 3) Run:

    python3 -m twine upload --repository testpypi dist/*

 4) enter "__token__" for the username and the API token as the password
 5) To install the py-vcon package from the testpypi repo to test it, run the following:

    pip3 install --index-url https://test.pypi.org/simple/ --extra-index-url https://pypi.org/simple/  py-vcon

 6) To test, install test dependencies (there should be some way to instruct pip to do this as these are in the setup file.  However, I have yet to figure it out):

    pip3 install pytest pytest-asyncio pytest-dependency pytest_httpserver

 7) copy tests and data files to a tmp directory to ensure the vcon package is not picked up

    mkdir -p /tmp/py_vcon_server
    cp -rp certs examples tests /tmp
    cp -rp py_vcon_server/tests /tmp/py_vcon_server

For the real/public repo, use the above steps, but substitute step 1 and 3 with the following:

    Go to https://pypi.org/manage/account/

    python3 -m twine upload dist/*

Commit all of the changes and tag the build release:

    git tag -a python-vcon_x.x.x_build [xxxxx_commit_SHA] -m "Vcon pypi release"

