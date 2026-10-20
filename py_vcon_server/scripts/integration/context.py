# Copyright (C) 2023-2026 SIPez LLC.  All rights reserved.
"""
integration/context.py -- Shared test context passed to every stage.
"""


class Context:
  """
  Holds all shared state for the integration test run.
  Passed to every stage's run() method.
  Stages read from context but do not start or stop the server --
  that is the runner's responsibility via server_manager.
  """

  def __init__(
      self,
      base_url,
      num_workers,
      env,
      results,
      server_manager,
      vcon_storage_url,
      project_root,
    ):
    self.base_url = base_url
    self.num_workers = num_workers
    self.env = env
    self.results = results
    self.server_manager = server_manager
    self.vcon_storage_url = vcon_storage_url
    self.project_root = project_root
