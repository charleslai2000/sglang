"""Explicit, fail-closed opt-in process hook installer for diagnostic-only run."""
import os
if os.getenv('GEMMA4_RUNTIME_HOOK_ENABLE')=='1':
 import runpy
 runpy.run_path(os.environ['GEMMA4_RUNTIME_HOOK_INSTALL'],run_name='__gemma4_runtime_hook_install__')
