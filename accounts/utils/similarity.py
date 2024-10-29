import logging
import re
from difflib import SequenceMatcher

logger = logging.getLogger(__name__)

whitespace_regex = re.compile(r"\s+")


def clean_persian_name(name: str):
    if not name:
        return name

    mapping = {
        'ك': 'ک',
        'ي': 'ی',
        'أ': 'ا',
        'ۀ': 'ه',
        'ء': '',
        'ّ': '',
        'َ': '',
        'ِ': '',
        'ُ': '',
        'ً': '',
        'ٍ': '',
        'ٌ': '',
        'ْ': '',
        'ؤ': 'و',
        'ئ': 'ی',
        'إ': 'ا',
        'آ': 'ا',
        'ة': 'ه',
        'ٓ': '',
        'ٰ': '',
        'ٔ': '',
        'ﻓ': 'ف',
        'ﻌ': 'ع',
        'ﺎ': 'ا',
        'ﻝ': 'ل'
    }

    name = name.translate(str.maketrans(mapping)).strip()
    return whitespace_regex.sub(' ', name)


def str_similar_rate(a: str, b: str) -> float:
    return SequenceMatcher(None, a, b).ratio()


def rotate_words(s: str) -> str:
    parts = s.split(' ')
    rotated = parts[-1:] + parts[:-1]
    return ' '.join(rotated)


NAME_SIMILARITY_THRESHOLD = 0.79


def name_similarity(name1, name2):
    name1, name2 = clean_persian_name(name1), clean_persian_name(name2)

    words1 = len(name1.split(' '))

    for i in range(words1):
        verified = str_similar_rate(name1, name2) >= NAME_SIMILARITY_THRESHOLD

        if verified:
            return True

        name1 = rotate_words(name1)

    name1_parts = name1.split(' ')
    name2_parts = name2.split(' ')

    if len(name1_parts) != name2_parts:
        small, long = name1_parts, name2_parts

        if len(small) > len(long):
            small, long = long, small

        if str_similar_rate(' '.join(small), ' '.join(long[:len(small)])) >= NAME_SIMILARITY_THRESHOLD:
            return True

    logger.info('verifying %s and %s is %s' % (name1, name2, False))

    return False


MULTI_WORD_NAMES = [
    'امیر رضا', 'امیر حسین', 'محمد حسین', 'روح الله', 'امیر علی', 'محمد حسن', 'قدم خیر', 'امیر مهدی', 'نازنین زهرا', 'محمد مهدی', 'محمد رضا'
]


def split_names(name: str) -> tuple:
    name = clean_persian_name(name)
    multi_word_names = list(map(lambda n: tuple(n.split(' ')), MULTI_WORD_NAMES))

    parts = name.split(' ')

    first_index = 0
    words = len(parts)

    if words - first_index > 2 and parts[first_index] in ('سید', 'سیده'):
        first_index += 1

    if words - first_index > 2 and len(parts[first_index]) <= 1:
        first_index += 1

    if words - first_index > 2 and (parts[first_index + 0], parts[first_index + 1]) in multi_word_names:
        first_index += 1

    return ' '.join(parts[:first_index + 1]), ' '.join(parts[first_index + 1:])
