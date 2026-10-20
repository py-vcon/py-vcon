# Build Instructions

  + [Building Vcon packages](#building-vcon-packages)
  + [Building the Vcon Server package](py_vcon_server/BUILD.md)

## Building Vcon packages

There are three Vcon packages, each a superset of the previous:

  * **python-vcon-core** - core vCon manipulation with no ML or external API filter plugin dependencies
  * **python-vcon-light** - adds Deepgram and OpenAI filter plugins; depends on python-vcon-core
  * **python-vcon** - full package including Whisper and PII redaction plugins; depends on python-vcon-light

All three packages are built from the same source tree and share the same version number.
Each higher tier package declares a minimum version dependency on the tier below it equal to its own
version, ensuring consistent package versions are always installed together.

Make sure python build and twine packages are installed:

    pip3 install --upgrade build twine

Create a clean clone of the branch that you want to build as any files in your development area
may get accidentally included in the vcon package:

    git clone https://github.com/py-vcon/py-vcon.git
    git checkout [xxxxx_commit_SHA]

Update the package __version__ number in vcon/__init__.py

Be sure to clean out the dist and egg directories:

    rm -rf dist python_vcon.egg-info python_vcon_core.egg-info python_vcon_light.egg-info

Build all three packages. They must be built in order from lowest to highest tier.

Each package can be built individually:

    python3 setup_core.py sdist bdist_wheel
    python3 setup_light.py sdist bdist_wheel
    python3 -m build

This creates sub-directory dist containing (x.x.x in the names below represents the build version number):

  * python_vcon_core-x.x.x-py3-none-any.whl
  * python_vcon_core-x.x.x.tar.gz
  * python_vcon_light-x.x.x-py3-none-any.whl
  * python_vcon_light-x.x.x.tar.gz
  * python_vcon-x.x.x-py3-none-any.whl
  * python_vcon-x.x.x.tar.gz

Test your package files on a clean VM or Docker container following
[these instructions](README.md#testing-the-vcon-package) after installing the desired vCon package
(replacing x.x.x with the build version number):

    # To test the core package:
    pip3 install dist/python_vcon_core-x.x.x.tar.gz

    # To test the light package (installs core automatically):
    pip3 install dist/python_vcon_light-x.x.x.tar.gz

    # To test the full package (installs core and light automatically):
    pip3 install dist/python_vcon-x.x.x.tar.gz

Push the package install files up to the pypi repo.
Packages must be uploaded in order from lowest to highest tier so that each package's
dependency on the tier below it can be resolved at install time.

For the test repo:

 1) Go to https://test.pypi.org/manage/account/
 2) Create an API token
 3) Upload in order, lowest tier first:

    python3 -m twine upload --repository testpypi dist/python?vcon?core-x.x.x*
    python3 -m twine upload --repository testpypi dist/python?vcon?light-x.x.x*
    python3 -m twine upload --repository testpypi dist/python?vcon-x.x.x*

    Note: twine will prompt for credentials separately for each of the three upload commands.
    To avoid repeated prompts, you can store your API token in ~/.pypirc:

        [distutils]
        index-servers = pypi

        [pypi]
        username = __token__
        password = pypi-your-api-token-here

    For the test repo, use:

        [distutils]
        index-servers =
            pypi
            testpypi

        [testpypi]
        username = __token__
        password = pypi-your-api-token-here

    See https://twine.readthedocs.io/en/stable/#configuration for full details.
    Protect this file as it contains your API token:

        chmod 600 ~/.pypirc

 4) enter "__token__" for the username and the API token as the password for each prompt
 5) To install the desired py-vcon package from the testpypi repo to test it, run the following
    (replacing PACKAGE_NAME with python-vcon-core, python-vcon-light, or python-vcon):

    pip3 install --index-url https://test.pypi.org/simple/ --extra-index-url https://pypi.org/simple/ PACKAGE_NAME

 6) To test, install test dependencies (there should be some way to instruct pip to do this as
    these are in the setup file.  However, I have yet to figure it out):

    pip3 install pytest pytest-asyncio pytest-dependency pytest_httpserver

 7) copy tests and data files to a tmp directory to ensure the vcon package is not picked up:

    mkdir -p /tmp/py_vcon_server && cp -rp certs examples tests /tmp && cp -rp py_vcon_server/tests /tmp/py_vcon_server

For the real/public repo, use the above steps, but substitute step 1 and 3 with the following:

    Go to https://pypi.org/manage/account/

    python3 -m twine upload dist/python?vcon?core-x.x.x*
    python3 -m twine upload dist/python?vcon?light-x.x.x*
    python3 -m twine upload dist/python?vcon-x.x.x*

    Note: twine will prompt for credentials separately for each of the three upload commands.
    To avoid repeated prompts, you can store your API token in ~/.pypirc:

        [distutils]
        index-servers = pypi

        [pypi]
        username = __token__
        password = pypi-your-api-token-here

    For the test repo, use:

        [distutils]
        index-servers =
            pypi
            testpypi

        [testpypi]
        username = __token__
        password = pypi-your-api-token-here

    See https://twine.readthedocs.io/en/stable/#configuration for full details.
    Protect this file as it contains your API token:

        chmod 600 ~/.pypirc

Commit all of the changes and tag the build release:

    git tag -a python-vcon_x.x.x_build [xxxxx_commit_SHA] -m "Vcon pypi release"
    git push origin python-vcon_x.x.x_build

