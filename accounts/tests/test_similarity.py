from django.test import TestCase

from accounts.utils.similarity import name_similarity


class SimilarityTestCase(TestCase):

    def test_name(self):
        self.assertTrue(name_similarity('علی امیرآبادی', 'علی امیرآبادی'))
        self.assertTrue(name_similarity('امیرآبادی علی', 'علی امیرآبادی'))
        self.assertTrue(name_similarity('امیرآبادی علی', 'علی امیرآبادی'))
        self.assertTrue(name_similarity('علی امیرآبادی', 'امیرآبادی علی'))
        self.assertTrue(name_similarity('نرگس خاتون عباسي اميري', 'عباسي اميري نرگس خاتون'))

        # self.assertFalse(name_similarity('علی عباسی', 'علی عباس زاده'))
        self.assertFalse(name_similarity('علیرضا حسینی', 'علی رضایی'))
