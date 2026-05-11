import os


def pytest_collection_modifyitems(items):
    order = ["test_broker", "test_worker", "test_haystack"]
    items.sort(key=lambda item: next(
        (i for i, name in enumerate(order) if name in item.nodeid),
        len(order)
    ))
