from datetime import datetime

from django.test import TestCase

from financial.utils.ach import next_ach_clear_time


class EstimateReceiveTimeTestCase(TestCase):

    def test_estimate_receive_time(self):
        test_times = {
            datetime(2023, 4, 26, 9, 00): datetime(2023, 4, 26, 11, 45),
            datetime(2023, 4, 26, 23, 1): datetime(2023, 4, 27, 4, 45),
            datetime(2023, 4, 27, 10, 30): datetime(2023, 4, 27, 14, 45),
            datetime(2023, 4, 28, 10, 30): datetime(2023, 4, 29, 4, 45),
        }

        for s, r in test_times.items():
            self.assertEqual(next_ach_clear_time(s.astimezone()), r.astimezone())
