
class BoolNode:
    AND = 'AND'
    OR = 'OR'

    default = AND

    CONDITIONS_LENGTH = None

    def __init__(self, *conditions):
        if self.CONDITIONS_LENGTH:
            assert len(conditions) == self.CONDITIONS_LENGTH, f'conditions should be of size={self.CONDITIONS_LENGTH}'

        self.is_connector = False

        if len(conditions) == 0:
            conditions = (None,)

        self.conditions = conditions
        self.inverted = False

    def change_to_connector(self, action, left_node: 'BoolNode', right_node: 'BoolNode'):
        self.is_connector = True
        self.action = action
        self.left_node = left_node
        self.right_node = right_node

    def __and__(self, other):
        connector = type(self)()
        connector.change_to_connector(self.AND, self, other)
        return connector

    def __or__(self, other):
        connector = type(self)()
        connector.change_to_connector(self.OR, self, other)
        return connector

    def __invert__(self):
        self.inverted = not self.inverted
        return self

    def leaf_evaluator(*args, **kwargs):
        raise NotImplemented

    def evaluate(self, *args, **kwargs):

        if self.is_connector:
            left_result = self.left_node.evaluate(*args, **kwargs)
            right_result = self.right_node.evaluate(*args, **kwargs)

            if self.action == self.AND:
                connector_result = left_result and right_result
            else:
                connector_result = left_result or right_result

            return connector_result ^ self.inverted

        else:
            return self.__evaluate_leaf__(*args, **kwargs)

    def __evaluate_leaf__(self, *args, **kwargs):
        if self.default == self.AND:
            for condition in self.conditions:
                if not self.leaf_evaluator(*args, **kwargs, condition=condition):
                    return self.inverted

            return not self.inverted

        else:
            for condition in self.conditions:
                if self.leaf_evaluator(*args, **kwargs, condition=condition):
                    return not self.inverted

            return self.inverted
