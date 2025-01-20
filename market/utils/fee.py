from accounts.models import SystemConfig


def is_fee_type_add_paying():
    return SystemConfig.get_system_config().commission_type == SystemConfig.FEE_ADD_PAYING
