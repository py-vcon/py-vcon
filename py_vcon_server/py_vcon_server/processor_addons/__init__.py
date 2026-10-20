# Namespace package: lets add-on distributions contribute modules to this package.
# (pkgutil style; setuptools' pkg_resources.declare_namespace was removed in setuptools 81)
__path__ = __import__('pkgutil').extend_path(__path__, __name__)
