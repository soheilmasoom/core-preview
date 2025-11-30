from ._generator_ import admin_field_generator


def general(verbose_name="", html=False, boolean=False, path_to_field=None, limit=-1,
            wrap_white_space=True):

    return admin_field_generator(
        verbose_name=verbose_name,
        html=html,
        boolean=boolean,
        path_to_field=path_to_field,
        limit=limit,
        wrap_white_space=wrap_white_space
    )
