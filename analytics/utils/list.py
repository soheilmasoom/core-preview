from typing import List


def join_lists_with_first_element(list1: List[tuple], list2: List[tuple], n1: int, n2: int, group_len: int = 1):

    assert n1 > 0 and n2 > 0
    assert group_len > 0

    map1 = {tuple(r[i] for i in range(group_len)): r for r in list1}
    map2 = {tuple(r[i] for i in range(group_len)): r for r in list2}

    empty1 = ('', ) * n1
    empty2 = ('', ) * n2

    result = []

    for key, r1 in map1.items():
        result.append(
            (*r1, *map2.get(key, empty2)[group_len:])
        )

    for key, r2 in map2.items():
        if key not in map1:
            result.append(
                (*key, *empty1[:-group_len], *map2[key][len(key):])
            )

    return result
