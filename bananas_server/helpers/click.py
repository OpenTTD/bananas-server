import importlib


def import_module(prefix, class_name):
    def _callback(value):
        value = value.lower()
        module = importlib.import_module(f"{prefix}.{value}")
        class_ = getattr(module, class_name)
        return class_

    def callback(ctx, param, value):
        if isinstance(value, tuple):
            return [_callback(v) for v in value]
        else:
            return _callback(value)

    return callback


def click_additional_options(additional_func):
    def decorator(func):
        additional_params = []
        for param in getattr(additional_func, "__click_params__", []):
            additional_params.append(param.name)

        def inner_decorator(**kwargs):
            additional_kwargs = {param: kwargs[param] for param in additional_params}
            additional_func(**additional_kwargs)

            # Remove the kwargs that are consumed by the additional_func
            [kwargs.pop(kwarg) for kwarg in additional_kwargs]

            func(**kwargs)

        inner_decorator.__click_params__ = getattr(func, "__click_params__", []) + getattr(
            additional_func, "__click_params__", []
        )
        inner_decorator.__doc__ = func.__doc__
        return inner_decorator

    return decorator
