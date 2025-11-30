from ._generator_ import admin_field_generator


def number(verbose_name="", path_to_field=None, wrap_white_space=True, split_length=3,
           splitter=','):

    def function_changer(func, admin, instance):

        amount = func(admin, instance)

        if amount is not None:
            return amount

        else:
            return ''

    return admin_field_generator(
        verbose_name=verbose_name,
        path_to_field=path_to_field,
        function_changer=function_changer,
        wrap_white_space=wrap_white_space
    )

