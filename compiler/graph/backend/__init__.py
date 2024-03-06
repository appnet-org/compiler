from __future__ import annotations

import importlib
import os
from pathlib import Path
from typing import Dict

from compiler.graph.ir import GraphIR

BACKEND_CONFIG_DIR = os.path.join(Path(__file__).parent, "config")


def scriptgen(
    girs: Dict[str, GraphIR],
    backend: str,
    app_name: str,
    app_manifest_file: str,
    app_edges: list,
):
    """
    Call corresponding script generation procedure according to the backend name.

    Args:
        girs: A dictionary mapping edge name to corresponding graphir.
        backend: backend name.
        app_name: the name of the application (for naming)
        app_manifest_file: the path to the application manifest file
        app_edges: the communication edges of the application
    """
    try:
        module = importlib.import_module(f"compiler.graph.backend.{backend}")
    except:
        raise ValueError(f"backend {backend} not supported")
    generator = getattr(module, f"scriptgen_{backend}")
    generator(girs, app_name, app_manifest_file, app_edges)
