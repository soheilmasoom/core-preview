import unittest

from analytics.utils.join import join_lists_with_first_element


class TestJoinListsWithFirstElement(unittest.TestCase):
    def test_matching_keys(self):
        """Test with matching keys in both lists."""
        list1 = [('a', 1), ('b', 2)]
        list2 = [('a', 3), ('b', 4)]
        n1 = len(list1[0])
        n2 = len(list2[0])
        expected = [
            ('a', 1, 3),
            ('b', 2, 4)
        ]
        result = join_lists_with_first_element(list1, list2, n1, n2)
        self.assertEqual(result, expected)

    def test_non_matching_keys(self):
        """Test with keys that do not match between lists."""
        list1 = [('a', 1), ('b', 2)]
        list2 = [('c', 3), ('d', 4)]
        n1 = len(list1[0])
        n2 = len(list2[0])
        expected = [
            ('a', 1, ''),
            ('b', 2, ''),
            ('', 'c', 3),
            ('', 'd', 4)
        ]
        result = join_lists_with_first_element(list1, list2, n1, n2)
        # Sorting the results because order may vary
        self.assertEqual(sorted(result), sorted(expected))

    def test_partial_matching_keys(self):
        """Test with some matching and some non-matching keys."""
        list1 = [('a', 1), ('b', 2)]
        list2 = [('b', 3), ('c', 4)]
        n1 = len(list1[0])
        n2 = len(list2[0])
        expected = [
            ('a', 1, ''),
            ('b', 2, 3),
            ('', 'c', 4)
        ]
        result = join_lists_with_first_element(list1, list2, n1, n2)
        self.assertEqual(sorted(result), sorted(expected))

    def test_empty_list1(self):
        """Test with an empty first list."""
        list1 = []
        list2 = [('a', 1), ('b', 2)]
        n1 = 2  # Expected size of tuples in list1
        n2 = len(list2[0])
        expected = [
            ('', 'a', 1),
            ('', 'b', 2)
        ]
        result = join_lists_with_first_element(list1, list2, n1, n2)
        self.assertEqual(sorted(result), sorted(expected))

    def test_empty_list2(self):
        """Test with an empty second list."""
        list1 = [('a', 1), ('b', 2)]
        list2 = []
        n1 = len(list1[0])
        n2 = 2  # Expected size of tuples in list2
        expected = [
            ('a', 1, ''),
            ('b', 2, '')
        ]
        result = join_lists_with_first_element(list1, list2, n1, n2)
        self.assertEqual(result, expected)

    def test_both_empty_lists(self):
        """Test with both lists empty."""
        list1 = []
        list2 = []
        n1 = 2  # Expected size of tuples in list1
        n2 = 2  # Expected size of tuples in list2
        expected = []
        result = join_lists_with_first_element(list1, list2, n1, n2)
        self.assertEqual(result, expected)

    def test_duplicate_keys_in_list1(self):
        """Test with duplicate keys in the first list."""
        list1 = [('a', 1), ('a', 2)]
        list2 = [('a', 3)]
        n1 = len(list1[0])
        n2 = len(list2[0])
        # Only the last occurrence of 'a' in list1 will be used
        expected = [
            ('a', 2, 3)
        ]
        result = join_lists_with_first_element(list1, list2, n1, n2)
        self.assertEqual(result, expected)

    def test_duplicate_keys_in_list2(self):
        """Test with duplicate keys in the second list."""
        list1 = [('a', 1)]
        list2 = [('a', 2), ('a', 3)]
        n1 = len(list1[0])
        n2 = len(list2[0])
        # Only the last occurrence of 'a' in list2 will be used
        expected = [
            ('a', 1, 3)
        ]
        result = join_lists_with_first_element(list1, list2, n1, n2)
        self.assertEqual(result, expected)

    def test_mismatched_tuple_lengths(self):
        """Test with tuples of different lengths."""
        list1 = [('a', 1)]
        list2 = [('a', 2, 3)]
        n1 = len(list1[0])  # 2
        n2 = len(list2[0])  # 3
        expected = [
            ('a', 1, 2, 3)
        ]
        result = join_lists_with_first_element(list1, list2, n1, n2)
        self.assertEqual(result, expected)

    def test_additional_fields_in_list2(self):
        """Test with additional fields in list2 tuples."""
        list1 = [('a', 1)]
        list2 = [('a', 2, 3, 4)]
        n1 = len(list1[0])  # 2
        n2 = len(list2[0])  # 4
        expected = [
            ('a', 1, 2, 3, 4)
        ]
        result = join_lists_with_first_element(list1, list2, n1, n2)
        self.assertEqual(result, expected)

    def test_missing_keys_in_list2(self):
        """Test when list2 is missing some keys from list1."""
        list1 = [('a', 1), ('b', 2)]
        list2 = [('a', 3)]
        n1 = len(list1[0])  # 2
        n2 = len(list2[0])  # 2
        expected = [
            ('a', 1, 3),
            ('b', 2, '')
        ]
        result = join_lists_with_first_element(list1, list2, n1, n2)
        self.assertEqual(result, expected)

    def test_missing_keys_in_list1(self):
        """Test when list1 is missing some keys from list2."""
        list1 = [('a', 1)]
        list2 = [('a', 3), ('b', 4)]
        n1 = len(list1[0])  # 2
        n2 = len(list2[0])  # 2
        expected = [
            ('a', 1, 3),
            ('', 'b', 4)
        ]
        result = join_lists_with_first_element(list1, list2, n1, n2)
        self.assertEqual(sorted(result), sorted(expected))
