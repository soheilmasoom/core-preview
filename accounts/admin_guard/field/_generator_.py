

def admin_field_generator(verbose_name, function_changer=None, path_to_field=None, html=False,
                          boolean=False, limit=-1, wrap_white_space=True):
    """
    This function generates admin_get decorators for being used in admin.py field methods.
    :param function_changer: this function holds the main logic of our decorator. This function has three \
    parameters: func, admin_inst, model_inst. func is the function defined in admin.py which take two arguments
    admin_inst and model inst
    :param path_to_field: a path for accessing field from model_inst provided in func
    Article with an CharField named `title`, model_field_name would be 'title'
    :param html: a boolean which indicates it has html content or no
    :param verbose_name: if provided it would be the verbose_name of column
    :param boolean: a boolean field which indicates that the output of func is boolean or no
    :param limit: max number of characters
    :param wrap_white_space: should wrap white space or not
    :return:
    """

    def default_function_changer(func, admin_inst, model_inst):
        """
        the default function changer which simply returns func's output

        :param func: this is a function which is defined in admin.py (under decorators)
        :param admin_inst: admin instance
        :param model_inst: model instance
        :return: a string used to show in admin panel
        """
        return func(admin_inst, model_inst)

    def inner(func):
        """
        :param func: the actual function defined in admin.py
        :return: datetime
        """

        def wrapped(admin_inst, model_inst):
            """
            This function is called by django when creating fields
            :param admin_inst: admin instance
            :param model_inst: the model instance
            :return: a string to show in django panel
            """

            if not verbose_name and path_to_field:
                wrapped.short_description = model_inst._meta.get_field(path_to_field).verbose_name

            if function_changer:
                result = function_changer(func, admin_inst, model_inst)
            else:
                result = default_function_changer(func, admin_inst, model_inst)

            if limit >= 0:
                if html:
                    raise Exception("Cannot set limit on html fields")

                elif len(result) > limit:
                    result = result[:limit] + '...'

            if not wrap_white_space:
                result = "<span style='white-space: nowrap;'>%s</span>" % result

            return result

        if verbose_name:
            wrapped.short_description = verbose_name

        else:
            wrapped.short_description = ""

        if path_to_field:
            wrapped.admin_order_field = path_to_field

        wrapped.allow_tags = html or not wrap_white_space
        wrapped.boolean = boolean

        return wrapped

    return inner

