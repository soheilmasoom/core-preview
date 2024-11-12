import dataclasses
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
        'ﻝ': 'ل',
        'ٸ': 'ی',
        '\u200c': ''
    }

    name = name.translate(str.maketrans(mapping)).strip()
    return whitespace_regex.sub(' ', name)


def remove_persian_pre_postfix(name: str):
    no_space = name.replace(' ', '')

    if len(no_space) >= 6 and name.startswith('سیده'):
        return name[4:]
    elif len(no_space) >= 5 and name.startswith('سید'):
        return name[3:]
    else:
        return name


def has_persian_pre_postfix(name: str):
    return remove_persian_pre_postfix(name) != name


def str_similar_rate(a: str, b: str) -> float:
    score = SequenceMatcher(None, a, b).ratio()
    # print(f"Similarity {a} <> {b} score: {score}")
    return score


def rotate_words(s: str) -> str:
    parts = s.split(' ')
    rotated = parts[-1:] + parts[:-1]
    return ' '.join(rotated)


NAME_SIMILARITY_THRESHOLD = 0.95


@dataclasses.dataclass
class Score:
    score: float
    valid: bool

    def __bool__(self):
        return self.valid


def name_similarity(name1, name2) -> Score:
    name1, name2 = clean_persian_name(name1), clean_persian_name(name2)
    if len(name1.replace(' ', '')) < 4 or len(name2.replace(' ', '')) < 4:
        return Score(score=0, valid=False)

    words1 = len(name1.split(' '))

    max_score = 0

    for i in range(words1):
        score = str_similar_rate(name1.replace(' ', ''), name2.replace(' ', ''))

        if score > max_score:
            max_score = score

        if score >= NAME_SIMILARITY_THRESHOLD:
            return Score(
                score=score,
                valid=True
            )

        name1 = rotate_words(name1)

    name1_parts = name1.split(' ')
    name2_parts = name2.split(' ')

    if len(name1_parts) != name2_parts:
        small, long = name1_parts, name2_parts

        if len(small) > len(long):
            small, long = long, small

        score = str_similar_rate(''.join(small).replace(' ', ''), ''.join(long[:len(small)]).replace(' ', ''))
        if score > max_score:
            max_score = score

        if score >= NAME_SIMILARITY_THRESHOLD:
            return Score(
                score=score,
                valid=True
            )

    if has_persian_pre_postfix(name1) or has_persian_pre_postfix(name2):
        return name_similarity(remove_persian_pre_postfix(name1), remove_persian_pre_postfix(name2))

    return Score(
        score=max_score,
        valid=False
    )


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
