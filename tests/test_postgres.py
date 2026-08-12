from concurrent.futures import ThreadPoolExecutor

import pytest
from django.db import IntegrityError, connections
from django.db.migrations.executor import MigrationExecutor

from contextloom.knowledge.models import Category


@pytest.mark.django_db
def test_all_migrations_are_applied():
    executor = MigrationExecutor(connections["default"])
    assert not executor.migration_plan(executor.loader.graph.leaf_nodes())


@pytest.mark.django_db(transaction=True)
def test_concurrent_duplicate_root_category_is_prevented(user):
    def create_root():
        try:
            Category.objects.create(owner_id=user.pk, name="Concurrent")
            return True
        except IntegrityError:
            return False
        finally:
            connections.close_all()

    with ThreadPoolExecutor(max_workers=2) as pool:
        outcomes = list(pool.map(lambda _: create_root(), range(2)))
    assert sorted(outcomes) == [False, True]
    assert Category.objects.filter(owner=user, name="Concurrent").count() == 1
    connections["default"].close()
