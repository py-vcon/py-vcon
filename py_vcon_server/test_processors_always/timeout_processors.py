# Copyright (C) 2023-2026 SIPez LLC.  All rights reserved.
"""
Test processors for timeout testing.

These processors are loaded via the PLUGIN_PATHS mechanism
so that REST API routes are created for them.
"""
import time
import asyncio
import pydantic
import py_vcon_server.processor

__version__ = "0.0.1"


# ============================================================
#  SleepAsync - timeout CAN interrupt
# ============================================================

class SleepAsyncOptions(py_vcon_server.processor.VconProcessorOptions):
    """Options for SleepAsyncProcessor."""
    sleep_seconds: float = pydantic.Field(
        title="seconds to sleep",
        description="Number of seconds to sleep asynchronously",
        default=1.0
    )


class SleepAsyncProcessor(py_vcon_server.processor.VconProcessor):
    """
    Processor that sleeps asynchronously.
    
    Timeout CAN interrupt this processor because it uses
    await asyncio.sleep() which yields to the event loop.
    """
    
    def __init__(self, init_options: py_vcon_server.processor.VconProcessorInitOptions):
        super().__init__(
            "Async Sleep Processor",
            "Sleeps asynchronously for testing timeouts",
            __version__,
            init_options,
            SleepAsyncOptions,
            False  # does not modify vcons
        )
    
    async def process(
        self,
        processor_input: py_vcon_server.processor.VconProcessorIO,
        options: SleepAsyncOptions
    ) -> py_vcon_server.processor.VconProcessorIO:
        await asyncio.sleep(options.sleep_seconds)
        return processor_input


# ============================================================
#  SleepSync - timeout CANNOT interrupt
# ============================================================

class SleepSyncOptions(py_vcon_server.processor.VconProcessorOptions):
    """Options for SleepSyncProcessor."""
    sleep_seconds: float = pydantic.Field(
        title="seconds to sleep",
        description="Number of seconds to sleep synchronously",
        default=1.0
    )


class SleepSyncProcessor(py_vcon_server.processor.VconProcessor):
    """
    Processor that sleeps synchronously.
    
    Timeout CANNOT interrupt this processor because it uses
    time.sleep() which blocks the event loop.
    """
    
    def __init__(self, init_options: py_vcon_server.processor.VconProcessorInitOptions):
        super().__init__(
            "Sync Sleep Processor",
            "Sleeps synchronously for testing blocking behavior",
            __version__,
            init_options,
            SleepSyncOptions,
            False  # does not modify vcons
        )
    
    async def process(
        self,
        processor_input: py_vcon_server.processor.VconProcessorIO,
        options: SleepSyncOptions
    ) -> py_vcon_server.processor.VconProcessorIO:
        time.sleep(options.sleep_seconds)
        return processor_input


# ============================================================
#  Success - returns immediately
# ============================================================

class SuccessOptions(py_vcon_server.processor.VconProcessorOptions):
    """Options for SuccessProcessor."""
    pass


class SuccessProcessor(py_vcon_server.processor.VconProcessor):
    """
    Processor that returns immediately.
    
    Used to verify normal operation with timeout configured.
    """
    
    def __init__(self, init_options: py_vcon_server.processor.VconProcessorInitOptions):
        super().__init__(
            "Success Processor",
            "Returns immediately for testing normal operation",
            __version__,
            init_options,
            SuccessOptions,
            False  # does not modify vcons
        )
    
    async def process(
        self,
        processor_input: py_vcon_server.processor.VconProcessorIO,
        options: SuccessOptions
    ) -> py_vcon_server.processor.VconProcessorIO:
        return processor_input


# ============================================================
#  Exception - raises an exception
# ============================================================

class ExceptionOptions(py_vcon_server.processor.VconProcessorOptions):
    """Options for ExceptionProcessor."""
    message: str = pydantic.Field(
        title="exception message",
        description="Message for the exception to raise",
        default="Test exception"
    )


class ExceptionProcessor(py_vcon_server.processor.VconProcessor):
    """
    Processor that raises an exception.
    
    Used to verify exceptions propagate correctly and are
    not masked by timeout handling.
    """
    
    def __init__(self, init_options: py_vcon_server.processor.VconProcessorInitOptions):
        super().__init__(
            "Exception Processor",
            "Raises an exception for testing error handling",
            __version__,
            init_options,
            ExceptionOptions,
            False  # does not modify vcons
        )
    
    async def process(
        self,
        processor_input: py_vcon_server.processor.VconProcessorIO,
        options: ExceptionOptions
    ) -> py_vcon_server.processor.VconProcessorIO:
        raise Exception(options.message)


# ============================================================
#  Register all processors
# ============================================================

init_options = py_vcon_server.processor.VconProcessorInitOptions()

py_vcon_server.processor.VconProcessorRegistry.register(
    init_options,
    "timeout_test_sleep_async",
    "timeout_processors",
    "SleepAsyncProcessor"
)

py_vcon_server.processor.VconProcessorRegistry.register(
    init_options,
    "timeout_test_sleep_sync",
    "timeout_processors",
    "SleepSyncProcessor"
)

py_vcon_server.processor.VconProcessorRegistry.register(
    init_options,
    "timeout_test_success",
    "timeout_processors",
    "SuccessProcessor"
)

py_vcon_server.processor.VconProcessorRegistry.register(
    init_options,
    "timeout_test_exception",
    "timeout_processors",
    "ExceptionProcessor"
)
