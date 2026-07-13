"""Test setup.

The protocol tests import the standalone package `protocol` directly (without
going through `custom_components.souliss.__init__`, which needs Home Assistant
installed). Full integration tests require Python 3.13 and
pytest-homeassistant-custom-component matching the targeted HA release.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent / "custom_components" / "souliss"))
