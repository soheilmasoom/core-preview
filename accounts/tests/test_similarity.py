from django.test import TestCase

from accounts.utils.similarity import name_similarity
import csv


def get_correct_samples():
    with open("accounts/tests/correct_names_sample.csv", mode="r") as file:
        csv_reader = csv.DictReader(file)
        return [dict(row) for row in csv_reader]


def get_correct_samples_error_rate() -> float:
    names = get_correct_samples()
    wrong = []
    for a in names:
        s = name_similarity(a['first_name1'] + ' ' + a['last_name1'], a['first_name2'] + ' ' + a['last_name2'])
        if not s:
            wrong.append(a)

    error_rate = len(wrong) / len(names)
    print(f'Error: {round(error_rate * 100, 2)}%')

    return error_rate


class SimilarityTestCase(TestCase):

    def test_name(self):
        self.assertTrue(name_similarity('علی امیرآبادی', 'علی امیرآبادی'))
        self.assertTrue(name_similarity('امیرآبادی علی', 'علی امیرآبادی'))
        self.assertTrue(name_similarity('امیرآبادی علی', 'علی امیرآبادی'))
        self.assertTrue(name_similarity('علی امیرآبادی', 'امیرآبادی علی'))
        self.assertTrue(name_similarity('نرگس خاتون عباسي اميري', 'عباسي اميري نرگس خاتون'))
        self.assertTrue(name_similarity('قنبري مصطفي', 'مصطفی‌ قنبری‌'))

        self.assertFalse(name_similarity('علیرضا حسینی', 'علی رضایی'))
        self.assertFalse(name_similarity('طه منصورزاده اشکانی', 'نیما منصورزاده اشکانی'))
        self.assertFalse(name_similarity('علی عباسی', 'علی عباس زاده'))

    def test_correct_samples(self):
        self.assertLess(get_correct_samples_error_rate(), 0.02)
