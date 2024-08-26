from django.contrib.postgres.search import SearchVector
from django.db.models import Q

from ledger.models import Asset
from ledger.models.asset import AssetSerializerMini
from market.models import PairSymbol
from market.serializers.symbol_serializer import SymbolBriefStatsSerializer
from multimedia.models import Article
from multimedia.views.faq_view import ArticleSerializer
from stake.models import StakeOption
from stake.views.stake_option_view import StakeOptionSerializer


def search_market(queries):
    if not queries:
        return {}

    other_key = ['خرید', 'فروش', 'خریدن', 'فروختن']

    or_expression = Q()
    for query in queries:
        or_expression |= Q(search=query)

    queryset = PairSymbol.objects.filter(enable=True).annotate(
        search=SearchVector(
            'asset__name', 'asset__name_fa', 'asset__original_name_fa', 'asset__symbol',
            'asset__original_symbol', 'asset__trading_view_symbol'
        )
    ).filter(or_expression)

    flag = not queryset

    for k in queries:
        if flag:
            for i in other_key:
                if k in i:
                    queryset = PairSymbol.objects.filter(enable=True)
                    flag = False
                    break
        else:
            break

    serialized_data = SymbolBriefStatsSerializer(queryset[:3], many=True).data
    return serialized_data


def search_otc(queries):
    if not queries:
        return {}

    other_key = ['خرید', 'فروش', 'خریدن', 'فروختن']

    or_expression = Q()
    for query in queries:
        or_expression |= Q(search=query)

    queryset = Asset.objects.filter(enable=True).annotate(
        search=SearchVector(
            'name', 'name_fa', 'original_name_fa', 'symbol', 'original_symbol', 'trading_view_symbol'
        )
    ).filter(or_expression)

    flag = not queryset

    for k in queries:
        if flag:
            for i in other_key:
                if k in i:
                    queryset = Asset.objects.filter(enable=True)
                    flag = False
                    break
        else:
            break

    serialized_data = AssetSerializerMini(queryset[:3], many=True).data
    return serialized_data


def search_staking(queries):
    if not queries:
        return {}

    other_key = ['استیکینگ',]

    or_expression = Q()
    for query in queries:
        or_expression |= Q(search=query)

    queryset = StakeOption.objects.filter(enable=True).annotate(
        search=SearchVector(
            'asset__name', 'asset__name_fa', 'asset__original_name_fa', 'asset__symbol',
            'asset__original_symbol', 'asset__trading_view_symbol'
        )
    ).filter(or_expression)

    flag = not queryset

    for k in queries:
        if flag:
            for i in other_key:
                if k in i:
                    queryset = StakeOption.objects.filter(enable=True)
                    flag = False
                    break
        else:
            break

    serialized_data = StakeOptionSerializer(queryset[:3], many=True).data
    return serialized_data


def search_faq(queries):
    if not queries:
        return {}

    or_expression = Q()
    for query in queries:
        or_expression |= Q(search=query)

    queryset = Article.objects.all().annotate(
        search=SearchVector(
            'title', 'title_en', '_content_text', 'parent__title', 'parent__title_en', 'parent__description'
        )
    ).filter(or_expression)

    serialized_data = ArticleSerializer(queryset[:3], many=True).data
    return serialized_data


def get_search_result(query):
    queries = [i for i in query.strip().split(' ')[:2] if i]

    market = search_market(queries)
    otc = search_otc(queries)
    staking = search_staking(queries)
    faq = search_faq(queries)

    return {
        "market": market,
        "otc": otc,
        "staking": staking,
        "faq": faq
    }
