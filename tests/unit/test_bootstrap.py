import importlib


def test_package_importable():
    module = importlib.import_module('awe_agentcheck')
    assert hasattr(module, '__version__')
