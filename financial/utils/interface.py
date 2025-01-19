from financial.exceptions import NoChannelError
from financial.interface import PayirChannel, ZibalChannel, JibitChannel, JibimoChannel, PaystarChannel, \
    ZibalBajehChannel, JibitChannelV2
from financial.interface.base_interface import BaseChannel
from financial.models import Gateway


def get_withdraw_channel(gateway: Gateway, verbose: bool = False) -> BaseChannel:
    mapping = {
        Gateway.PAYIR: PayirChannel,
        Gateway.ZIBAL: ZibalChannel,
        Gateway.JIBIT: JibitChannel,
        Gateway.JIBIT_V2: JibitChannelV2,
        Gateway.JIBIMO: JibimoChannel,
        Gateway.PAYSTAR: PaystarChannel,
        Gateway.ZIBAL_BAJEH: ZibalBajehChannel
    }

    channel_class = mapping.get(gateway.type)
    if not channel_class:
        raise NoChannelError

    return channel_class(gateway, verbose)