import importlib.util


def test_package_discoverable():
    assert importlib.util.find_spec("scheduler") is not None
