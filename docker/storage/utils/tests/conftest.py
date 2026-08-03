"""Put ``utils/`` on the path, which is how these scripts run: the container
invokes them as ``/utils/<script>``, so their own directory is ``sys.path[0]``
and ``storage_lib`` resolves as a sibling.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
