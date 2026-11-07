"""Check actual image policy after apply, all payloads, and FWZ reopening."""
from classe100x.payload import Context
from common import BOOT, OUTPUT, prerequisites, require_no_updater_links, require_pinned

c = Context()
prerequisites(c.image, c.data.get("environment", "main"))
for path, expected in OUTPUT.items():
    require_pinned(c.image, path, expected, 0o664, 1000)
c.image.require_absent(BOOT)
require_no_updater_links(c.image)
