# Build Instructions for vCon Server

## Building py_vcon_server package

Make sure python build and twine packages are installed:

    pip3 install --upgrade build twine

Create a clean clone of the branch that you want to build as any files in your development area may get accidently included in the vcon package:

    git clone https://github.com/py-vcon/py-vcon.git
    cd py-vcon
    git checkout [xxxxx_commit_SHA]
    cd py_vcon_server

Update the package __version__ number in vcon/vcon/__init__.py

Be sure to clean out the dist directory:

    rm -rf dist py_vcon_server.egg-info

In the py_vcon_server directory (root containing setup.py and py_vcon_server sub-directory):

    python3 -m build

This creates sub-directory dist containing (x.x.x in the names below represents the version number):

  * py_vcon_server-x.x.x-py3-none-any.whl
  * py_vcon_server-x.x.x.tar.gz

Test your package files on a clean VM or Docker container.
In preparation for testing, install your newly build server package:

    pip3 install dist/py_vcon_server-x.x.x.tar.gz

First follow the test file setup instructions for the[ python_vcon pagage testing](README.md#testing-the-vcon-package).
Then following [these instructions](README.md#testing-the-vcon-server) for test the server after installing the py_vcon_server package (replacing x.x.x with the build version number):


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

TODO: verify this
    mkdir -p /tmp/py_vcon_server
    mkdir -p /tmp/vcon/filter_plugins
    cp -rp certs examples tests /tmp
    cp -rp py_vcon_server/tests /tmp/py_vcon_server

For the real/public repo, use the above steps, but substitute step 1 and 3 with the following:

    Go to https://pypi.org/manage/account/

    python3 -m twine upload dist/*

Commit all of the changes and tag the build release:

    git tag -a py-vcon-server_x.x.x_build [xxxxx_commit_SHA] -m "Vcon Server pypi release"

Note: it may be necessary to push the tag.  You can test it out, before actually pushing using:

    git push --tags --dry-run

Then do it again without the --dry-run option if it looks right.

