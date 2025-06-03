
""" Registration for the example addon **VconProcessor** """
import py_vcon_server.processor

init_options = py_vcon_server.processor.VconProcessorInitOptions()

py_vcon_server.processor.VconProcessorRegistry.register(
      init_options,
      "my_proc",
      "py_vcon_server.processor_addons.my_proc_impl.my_proc",
      "MyProc"
      )

