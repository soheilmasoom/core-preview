from .bool_node import BoolNode


def get_value(admin, model, condition):
    if isinstance(condition, str):

        if model is None:
            return None

        if hasattr(admin, condition):
            admin_func = getattr(admin, condition, None)
            return admin_func(model)

        elif hasattr(model, condition):
            return getattr(model, condition)

        else:
            raise Exception('condition not found')

    elif callable(condition):
        return condition(admin, model)

    else:
        return condition


class Superuser(BoolNode):
    def leaf_evaluator(self, request, admin, model, condition):
        return request.user.is_superuser


class IsNone(BoolNode):
    def leaf_evaluator(self, request, admin, model, condition):
        return get_value(admin, model, condition) is None


class HasPerm(BoolNode):
    def leaf_evaluator(self, request, admin, model, condition):
        return request.user.has_perm(condition)


class M(BoolNode):
    superuser = Superuser()
    has_perm = HasPerm
    is_none = IsNone

    def leaf_evaluator(self, request, admin, model, condition):
        return get_value(admin, model, condition)

    @staticmethod
    def is_value(field, value):
        class IsValue(BoolNode):
            def leaf_evaluator(self, request, admin, model, condition):
                return get_value(admin, model, condition) == value

        return IsValue(field)
