from sentry.tsdb.base import TSDBModel
from sentry.tsdb.redissnuba import READ, method_specifications, selector_func
from sentry.tsdb.snuba import SnubaTSDB


def get_callargs(model):
    """
    Represents for all possible ways that a model could be passed to ``selector_func`` through the callargs
    """
    return {
        "model": model,
        "models": [model],
        "items": [(model, "key", ["values"])],
        "requests": [(model, "data")],
    }


def test_redissnuba_connects_to_correct_backend() -> None:
    should_resolve_to_redis = set(list(TSDBModel)) - set(SnubaTSDB.model_query_settings.keys())
    should_resolve_to_snuba = set(SnubaTSDB.model_query_settings.keys())

    # Assert redissnuba routes outcomes-based tsdb metrics to snuba
    assert TSDBModel.project_total_received in should_resolve_to_snuba
    assert TSDBModel.organization_total_received in should_resolve_to_snuba

    methods = set(method_specifications.keys()) - {"flush"}

    for method in methods:
        for model in should_resolve_to_redis:
            assert "redis" == selector_func(method, get_callargs(model))

        for model in should_resolve_to_snuba:
            read_or_write, _ = method_specifications[method]

            if read_or_write == READ:
                assert "snuba" == selector_func(method, get_callargs(model))
            else:
                assert "dummy" == selector_func(method, get_callargs(model))
