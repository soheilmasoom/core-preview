import os

from celery import Celery
from celery.schedules import crontab
from decouple import config
from django.conf import settings

os.environ.setdefault('DJANGO_SETTINGS_MODULE', '_base.settings')

app = Celery('exchange_core', broker=config('RABBITMQ_URL', default='pyamqp://guest@localhost//'))

# Using a string here means the worker doesn't have to serialize
# the configuration object to child processes.
# - namespace='CELERY' means all celery-related configuration keys
#   should have a `CELERY_` prefix.
app.config_from_object('django.conf:settings', namespace='CELERY')

# Load task modules from all registered Django apps.
app.autodiscover_tasks()

TASK_MULTIPLIER = 1

if settings.DEBUG_OR_TESTING_OR_STAGING:
    TASK_MULTIPLIER = 5


app.conf.beat_schedule = {
    'price_alert': {
        'task': 'ledger.tasks.alert.send_price_notifications',
        'schedule':  60 * 3 * TASK_MULTIPLIER,
        'options': {
            'queue': 'notif-manager',
            'expires': 90 * TASK_MULTIPLIER
        }
    },
    'update_network_fee': {
        'task': 'ledger.tasks.fee.update_network_fees',
        'schedule': crontab(minute="*/30"),
        'options': {
            'queue': 'celery',
            'expires': 30 * 60
        },
    },
    'auto_clear_debts': {
        'task': 'ledger.tasks.debt.auto_clear_debts',
        'schedule': 60 * TASK_MULTIPLIER,
        'options': {
            'queue': 'celery',
            'expires': 60 * TASK_MULTIPLIER
        },
    },
    # 'update_provider_withdraw': {
    #     'task': 'ledger.tasks.withdraw.update_provider_withdraw',
    #     'schedule': 10 * TASK_MULTIPLIER,
    #     'options': {
    #         'queue': 'transfer',
    #         'expires': 10 * TASK_MULTIPLIER
    #     },
    # },

    'update_withdraws': {
        'task': 'ledger.tasks.withdraw.update_withdraws',
        'schedule': 10 * TASK_MULTIPLIER,
        'options': {
            'queue': 'transfer',
            'expires': 10 * TASK_MULTIPLIER
        },
    },

    'update_distribution_factors': {
        'task': 'ledger.tasks.distribution.update_distribution_factors',
        'schedule': crontab(hour=21, minute=0),
        'options': {
            'queue': 'celery',
            'expires': 36000
        },
    },

    'create_stake_revenue': {
        'task': 'stake.tasks.revenue.create_stake_revenue',
        'schedule': crontab(hour=22, minute=0),
        'options': {
            'queue': 'celery',
            'expires': 36000
        },
    },
    'handle_stake_requests_status': {
        'task': 'stake.tasks.status.handle_stake_requests_status',
        'schedule': crontab(minute=30),
        'options': {
            'queue': 'celery',
            'expires': 3600
        },
    },

    'free_missing_locks': {
        'task': 'ledger.tasks.locks.free_missing_locks',
        'schedule': 15,
        'options': {
            'queue': 'celery',
            'expires': 15
        },
    },

    'pending_otc_trades': {
        'task': 'ledger.tasks.otc.accept_pending_otc_trades',
        'schedule': 30,
        'options': {
            'queue': 'celery',
            'expires': 30
        },
    },

    'limit_otc_requests': {
        'task': 'ledger.tasks.otc.handle_limit_otc_request',
        'schedule': 30,
        'options': {
            'queue': 'celery',
            'expires': 30
        },
    },

    'check_maker_order_price': {
        'task': 'market.tasks.order.check_maker_order_price',
        'schedule': 30,
        'options': {
            'queue': 'celery',
            'expires': 30
        },
    },

    'collect_margin_interest': {
        'task': 'ledger.tasks.margin.collect_margin_interest',
        'schedule': crontab(hour='4,12,20', minute=30),
        'options': {
            'queue': 'margin',
            'expires': 3600
        },
    },

    'terminate_positions': {
        'task': 'ledger.tasks.margin.terminate_positions',
        'schedule': 20 * TASK_MULTIPLIER,
        'options': {
            'queue': 'margin',
            'expires': 20 * TASK_MULTIPLIER
        },
    },

    'alert_risky_position': {
        'task': 'ledger.tasks.margin.alert_risky_position',
        'schedule': 20 * TASK_MULTIPLIER,
        'options': {
            'queue': 'margin',
            'expires': 20 * TASK_MULTIPLIER
        },
    },

    'check_position_health': {
        'task': 'ledger.tasks.margin.check_position_health',
        'schedule': 600 * TASK_MULTIPLIER,
        'options': {
            'queue': 'margin',
            'expires': 600 * TASK_MULTIPLIER
        },
    },

    'fill_trades_revenue': {
        'task': 'accounting.tasks.revenue.fill_revenue_filled_prices',
        'schedule': 120 * TASK_MULTIPLIER,
        'options': {
            'queue': 'celery',
            'expires': 120 * TASK_MULTIPLIER
        },
    },

    'update_fiat_withdraws': {
        'task': 'financial.tasks.withdraw.update_withdraws',
        'schedule': 10 * TASK_MULTIPLIER,
        'options': {
            'queue': 'finance',
            'expires': 10 * TASK_MULTIPLIER
        },
    },

    'update_withdraw_status': {
        'task': 'financial.tasks.withdraw.update_withdraw_status',
        'schedule': 300 * TASK_MULTIPLIER,
        'options': {
            'queue': 'finance',
            'expires': 300 * TASK_MULTIPLIER
        },
    },

    'handle_missing_payments': {
        'task': 'financial.tasks.gateway.handle_missing_payments',
        'schedule': 60 * TASK_MULTIPLIER,
        'options': {
            'queue': 'finance',
            'expires': 60 * TASK_MULTIPLIER
        },
    },

    'handle_missing_payment_ids': {
        'task': 'financial.tasks.gateway.handle_missing_payment_ids',
        'schedule': 30 * TASK_MULTIPLIER,
        'options': {
            'queue': 'finance',
            'expires': 30 * TASK_MULTIPLIER
        },
    },

    'update_accounts_pnl': {
        'task': 'ledger.tasks.pnl.create_pnl_histories',
        'schedule': crontab(hour=20, minute=30),
        'options': {
            'queue': 'history',
        }
    },

    'create_analytics': {
        'task': 'analytics.tasks.create_analytics',
        'schedule': crontab(hour=21, minute=0),
        'options': {
            'queue': 'history',
        }
    },

    'provider_income': {
        'task': 'accounting.tasks.provider.fill_provider_incomes',
        'schedule': crontab(minute=30),
        'options': {
            'queue': 'history',
            'expires': 3600,
        },
    },
    'blocklink_incomes': {
        'task': 'accounting.tasks.blocklink.fill_blocklink_incomes',
        'schedule': crontab(minute=30),
        'options': {
            'queue': 'history',
            'expires': 3600,
        },
    },

    'create_vault_snapshot': {
        'task': 'accounting.tasks.vault.update_vaults',
        'schedule': crontab(minute='*/5'),
        'options': {
            'queue': 'vault',
            'expires': 200
        }
    },

    'trigger_kafka_event': {
        'task': 'analytics.tasks.trigger_kafka_event',
        'schedule': 10,
        'options': {
            'queue': 'notif-manager',
            'expires': 12
        }
    },

    'send_notifications_push': {
        'task': 'accounts.tasks.notification.send_notifications_push',
        'schedule': 5 * TASK_MULTIPLIER,
        'options': {
            'queue': 'notif-manager',
            'expires': 60 * TASK_MULTIPLIER
        },
    },
    'process_bulk_notifications': {
        'task': 'accounts.tasks.notification.process_bulk_notifications',
        'schedule': 60 * TASK_MULTIPLIER,
        'options': {
            'queue': 'notif-manager',
            'expires': 60 * TASK_MULTIPLIER
        },
    },
    'send_sms_notifications': {
        'task': 'accounts.tasks.notification.send_sms_notifications',
        'schedule': 10 * TASK_MULTIPLIER,
        'options': {
            'queue': 'notif-manager',
            'expires': 60 * TASK_MULTIPLIER
        },
    },
    'send_email_notifications': {
        'task': 'accounts.tasks.notification.send_email_notifications',
        'schedule': 10 * TASK_MULTIPLIER,
        'options': {
            'queue': 'notif-manager',
            'expires': 60 * TASK_MULTIPLIER
        },
    },
    'ban_credit_deposits': {
        'task': 'accounts.tasks.fraud.ban_credit_deposit_of_free_riders',
        'schedule': crontab(hour=0, minute=30),
        'options': {
            'queue': 'celery',
        },
    },

    'expire_missions': {
        'task': 'gamify.tasks.deactivate_expired_missions',
        'schedule': crontab(hour=20, minute=30),
        'options': {
            'queue': 'celery',
            'expires': 3600
        },
    },
    'check_alerts': {
        'task': 'health.tasks.check_alerts',
        'schedule': crontab(minute='*'),
        'options': {
            'queue': 'alert',
            'expires': 60
        }
    },
    'check_conditional_price_alerts': {
        'task': 'ledger.tasks.alert.check_conditional_price_alerts',
        'schedule': crontab(minute=5),
        'options': {
            'queue': 'celery',
            'expires': 3600
        },
    },
    # 'trigger_fcm_topic_subscriptions': {
    #     'task': 'accounts.tasks.notification.manage_user_topic_subscription_task',
    #     'schedule': crontab(minute=5),
    #     'options': {
    #         'queue': 'notif-manager',
    #         'expires': 3600
    #     },
    # },
    'network_schedules': {
        'task': 'ledger.tasks.network.check_network_schedules',
        'schedule': crontab(minute='30'),
        'options': {
            'queue': 'celery',
            'expires': 3 * 3600
        }
    },
}

if 'marketing' in settings.INSTALLED_APPS:
    app.conf.beat_schedule.update({
        'fill_ads_reports': {
            'task': 'marketing.tasks.fill_ads_reports',
            'schedule': crontab(hour=22, minute=0),
            'options': {
                'queue': 'marketing',
                'expires': 3600 * TASK_MULTIPLIER
            }
        },
    })
