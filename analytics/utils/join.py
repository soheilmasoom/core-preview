from typing import List


def join_lists_with_first_element(list1: List[tuple], list2: List[tuple], n1, n2):
    assert n1 > 0 and n2 > 0

    map1 = {r[0]: r for r in list1}
    map2 = {r[0]: r for r in list2}

    empty1 = ('', ) * n1
    empty2 = ('', ) * n2

    result = []

    for key, r1 in map1.items():
        result.append(
            (*r1, *map2.get(key, empty2)[1:])
        )

    for key, r2 in map2.items():
        if key not in map1:
            result.append(
                (*empty1[:-1], *map2[key])
            )

    return result
