"""Opt-in live check with public place names only; never reads the user vault."""

import json
import sys
import time

from aitutor.addresses import AddressDirectory


def main():
    if "--live" not in sys.argv:
        raise SystemExit("Specify --live to contact the public Photon server.")
    directory = AddressDirectory()
    regions = directory.search("region", "Самарская")
    region = next(r for r in regions["items"] if r["name"] == "Самарская область")
    time.sleep(1.1)
    cities = directory.search("city", "Самара", region["id"])
    assert any(c["name"] == "Самара" for c in cities["items"])
    print(json.dumps({"passed": True, "region": region, "cities": cities}, ensure_ascii=True))


if __name__ == "__main__":
    main()
