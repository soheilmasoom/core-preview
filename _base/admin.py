from decimal import Decimal

from django.contrib import messages
from django.contrib.admin import AdminSite
from django_otp.admin import OTPAdminSite

from ledger.models import Asset
from ledger.utils.price import get_price, get_prices


class XAUMAdminSiteMixin:
    def index(self, request, extra_context=None):
        extra_context = extra_context or {}

        try:
            xaum_asset = Asset.objects.get(symbol='XAUM', enable=True)
            extra_context['xaum_asset'] = xaum_asset
            prices = get_prices(['XAUMIRT'], side='sell', allow_stale=True)
            if prices and 'XAUMIRT' in prices:
                extra_context['xaum_price'] = prices['XAUMIRT']
            else:
                extra_context['xaum_price'] = None

            if request.method == 'POST':
                if 'revert' in request.POST:
                    xaum_asset.revert_manual_pricing()
                    messages.success(request, 'قیمت گذاری به حالت خودکار تغییر کرد')
                else:
                    manual_pricing = request.POST.get('manual_pricing') == 'on'
                    price = request.POST.get('price')

                    if manual_pricing and price:
                        xaum_asset.set_manual_pricing(Decimal(price))
                        messages.success(request, f'قیمت دستی {price} ریال تنظیم شد')
                    elif not manual_pricing:
                        xaum_asset.revert_manual_pricing()
                        messages.success(request, 'قیمت گذاری به حالت خودکار تغییر کرد')
        except Asset.DoesNotExist:
            extra_context['xaum_asset'] = None

        return super().index(request, extra_context)


class CoreAdminSite(XAUMAdminSiteMixin, OTPAdminSite):
    pass


class DevAdminSite(XAUMAdminSiteMixin, AdminSite):
    pass
