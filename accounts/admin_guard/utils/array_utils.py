

def iterate(obj):
    try:
        iter(obj)

        return obj
    except:
        return [obj]


def foreach(context, func):
    """

    :param context: list or object
    :param func:
    :return:
    """
    try:
        iter(context)

        for c in context:
            func(c)
    except:
        func(context)


def append(iterator, obj, unique=False):

    if unique and obj in iterator:
        return iterator

    try:
        return iterator + (obj, )
    except:
        return iterator + [obj]


def append_list(iterator, obj_list, unique=False):
    for obj in obj_list:
        iterator = append(iterator, obj, unique=unique)

    return iterator
