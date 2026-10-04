"""dsh-chatgpt-bridge — let any DSH model drive the real ChatGPT sidebar.

The engine is :mod:`dsh_chatgpt_bridge.core`; :mod:`dsh_chatgpt_bridge.browser` drives any
Chromium window (used for the GitHub console work); :mod:`dsh_chatgpt_bridge.slicer` turns a
long screenshot into readable, uploadable slices.
"""

__version__ = "1.0.0"

from .core import (  # noqa: F401
    Emitter,
    InputAborted,
    InputLimits,
    Target,
    attached_count,
    composer_text,
    locate_sidebar,
    transcript_text,
    wait_for_reply,
)

__all__ = [
    "__version__",
    "Emitter",
    "InputAborted",
    "InputLimits",
    "Target",
    "attached_count",
    "composer_text",
    "locate_sidebar",
    "transcript_text",
    "wait_for_reply",
]
