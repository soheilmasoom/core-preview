# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

This is a Django-based cryptocurrency/precious metals exchange platform (Raastin). The system supports both crypto exchanges and precious metals trading, with the exchange type configured via the `EXCHANGE_TYPE` environment variable.

## Development Commands

### Environment Setup
```bash
# Link development environment file
ln -s .env.development .env

# Activate virtual environment
source venv/bin/activate

# Install dependencies
pip install -r requirements.txt
```

### Running the Application
```bash
# Run development server
python manage.py runserver

# Run with Gunicorn (production-like)
gunicorn --workers 10 --timeout 120 --bind 0.0.0.0:8000 _base.wsgi
```

### Database Operations
```bash
# Create migrations
python manage.py makemigrations

# Apply migrations
python manage.py migrate

# Create superuser
python manage.py createsuperuser

# Access Django shell
python manage.py shell
```

### Testing
```bash
# Run all tests
python manage.py test

# Run specific app tests
python manage.py test accounts
python manage.py test ledger
python manage.py test market

# Run specific test file
python manage.py test ledger.tests.test_withdraw

# Run specific test class or method
python manage.py test ledger.tests.test_withdraw.WithdrawTestCase
python manage.py test ledger.tests.test_withdraw.WithdrawTestCase.test_crypto_withdraw
```

### Celery (Async Tasks)
```bash
# Start Celery worker
celery -A _base worker -l info

# Start Celery beat scheduler
celery -A _base beat -l info

# Run worker for specific queue
celery -A _base worker -Q celery,finance,margin,transfer,notif-manager -l info
```

### Static Files & Localization
```bash
# Collect static files
python manage.py collectstatic

# Compile translation messages
python manage.py compilemessages
```

### Custom Management Commands
```bash
# Generate OTP for admin users
python manage.py make_otp_for_admin

# Setup MinIO storage
python manage.py setupminio

# Update market data in Redis
python manage.py update_market_redis

# Backfill OHLC data
python manage.py backfill_ohlc
```

## Architecture Overview

### Project Structure

- **`_base/`**: Core Django configuration (settings, URLs, Celery, WSGI)
- **`accounts/`**: User management, authentication, notifications, KYC/verification
- **`ledger/`**: Core financial ledger - wallets, deposits, withdrawals, transfers, OTC trades, margin trading
- **`market/`**: Trading engine - orders, trades, pair symbols, stop-loss, OCO orders
- **`financial/`**: Fiat payment integration - deposits, withdrawals, payment gateways
- **`accounting/`**: Internal accounting - revenue tracking, vault management, provider/blocklink income
- **`analytics/`**: Analytics, metrics collection, Kafka event streaming
- **`multimedia/`**: Media file management with MinIO integration
- **`stake/`**: Staking functionality for crypto assets
- **`gamify/`**: Gamification features (missions, prizes)
- **`ohlc/`**: OHLC (candlestick) chart data management
- **`treasury/`**: Treasury management
- **`engage/`**: User engagement features
- **`health/`**: System health checks and alerts
- **`search/`**: Search functionality
- **`marketing/`**: Marketing campaigns and ad reporting (Raastin-specific)

### Key Architectural Patterns

#### Multi-Exchange Type Support
The codebase supports both cryptocurrency and precious metals exchanges via `EXCHANGE_TYPE` environment variable:
- Exchange type is defined in `_base/utils.py` as `ExchangeType` enum
- Admin decorators: `@admin_register_for_crypto_exchange(Model)` and `@admin_register_for_precious_metals_exchange(Model)`
- Display decorators: `@admin_display_for_crypto(description="...")`
- Check `settings.EXCHANGE_TYPE.is_crypto` or `settings.EXCHANGE_TYPE.is_precious_metals` for conditional logic

#### Ledger System Architecture
The `ledger` app is the core financial system:
- **Wallet**: User balances for each asset (spot, margin, reserve wallets)
- **Asset/NetworkAsset**: Supported cryptocurrencies and their blockchain networks
- **Transfer**: Internal/external transfers, deposits, withdrawals
- **OTCRequest/OTCTrade**: Over-the-counter trading
- **MarginPosition**: Margin trading positions with leverage
- **BalanceLock**: Prevents double-spending by locking balances during operations
- **Trx**: Transaction records for all balance changes

#### Market Trading System
The `market` app handles order matching and execution:
- **PairSymbol**: Trading pairs (e.g., BTC/USDT)
- **Order**: Limit/market/stop-limit orders
- **Trade**: Executed trades resulting from matched orders
- **StopLoss/OCO**: Advanced order types
- Orders are matched and executed by an external matching engine (communicates via Redis)

#### Authentication & Authorization
- Custom JWT authentication: `accounts.authentication.CustomJWTAuthentication`
- Uses RSA256 signing with `JWT_PRIVATE_KEY`/`JWT_PUBLIC_KEY` from environment
- Custom user model: `accounts.User` (defined as `AUTH_USER_MODEL`)
- OTP/2FA support via `django_otp`
- Token blacklist support via `rest_framework_simplejwt.token_blacklist`

#### Async Task Processing (Celery)
Celery configuration in `_base/celery.py` with multiple queues:
- **`celery`**: General tasks (debt clearing, locks, OTC trades, market orders)
- **`finance`**: Fiat withdrawals, deposits, payment gateway updates
- **`transfer`**: Crypto withdrawals and network operations
- **`margin`**: Margin position management, liquidations, interest collection
- **`notif-manager`**: Push notifications, SMS, email, Telegram bot
- **`history`**: Analytics, PNL calculations, snapshots
- **`vault`**: Vault balance snapshots
- **`alert`**: System health monitoring
- **`marketing`**: Marketing campaign reports (if enabled)

Beat schedules are defined in the same file with different intervals for DEBUG/STAGING vs production.

#### Caching Strategy
Multiple Redis databases are used (see `settings.py`):
- DB 0: Default Django cache
- DB 1: Token cache
- DB 2: Price/ticker cache
- DB 3: Market cache
- DB 4: Metrics cache
- DB 5: FCM (Firebase Cloud Messaging) cache

#### Storage
- **Local development**: Django file storage
- **Production**: MinIO object storage (S3-compatible)
  - Configured via `MINIO_ENDPOINT`, `MINIO_ACCESS_KEY`, `MINIO_SECRET_KEY`
  - Separate buckets: `core-media` (private), `core-media-public`, `core-static`

### Special Accounts
The system uses special system accounts (configured via environment):
- `SYSTEM_ACCOUNT_ID`: System account for internal operations
- `OTC_ACCOUNT_ID`: Account for OTC trade facilitation
- `MARKET_MAKER_ACCOUNT_ID`: Market maker account
- `TRADER_ACCOUNT_ID`: Automated trader account
- `MARGIN_INSURANCE_ACCOUNT`: Insurance fund for margin trading
- `MARGIN_POOL_ACCOUNT`: Liquidity pool for margin trading
- `REVERT_HELPER_ACCOUNT`: Account for transaction reversals

### Feature Flags
Environment-based feature toggles:
- `TRADE_ENABLE`: Enable/disable trading
- `MARKET_TRADE_ENABLE`: Enable/disable market orders
- `WITHDRAW_ENABLE`: Enable/disable withdrawals

## Testing Notes

- Tests use the main database by default (can be optimized with `TEST.NAME` and `SERIALIZE: False`)
- `settings.TESTING` is automatically set to `True` when running tests
- Fake OTP generation is enabled in DEBUG/TESTING/STAGING environments
- Mock external services (payment gateways, blockchain providers) in tests

## Security Considerations

- CSRF is currently disabled via custom middleware (`accounts.middleware.DisableCsrfCheck`) - marked as TODO
- Database credentials are managed via environment variables (`.env` file)
- JWT keys should use RSA256 algorithm with 3072-bit keys (see README for generation)
- Service account key (`serviceAccountKey.json`) is in `.gitignore` - never commit
- Session cookies require HTTPS in production (`SESSION_COOKIE_SECURE=True`)

## Database Schema Notes

- Custom user model extends Django's AbstractUser: `accounts.User`
- Simple History tracking is enabled for audit trails (`django-simple-history`)
- Jalali date support for Iranian calendar display
- PostgreSQL-specific features used (JSON fields, transactions)
- Metabase read-only user setup documented in README.md

## External Integrations

- **RabbitMQ**: Message broker for Celery
- **Redis**: Caching and real-time market data
- **MinIO**: Object storage (production)
- **Sentry**: Error tracking and monitoring
- **Kafka**: Event streaming (optional, via `KAFKA_HOST_URL`)
- **Firebase**: Push notifications (FCM)
- **Kavenegar**: SMS provider
- **Payment Gateways**: Fiat deposit/withdrawal processing
- **Blockchain Providers**: Crypto deposit/withdrawal handling

## Code Conventions

- Models are split into separate files within `models/` directories
- Import models from `models/__init__.py` (e.g., `from ledger.models import Wallet`)
- Tasks are organized in `tasks/` directories by function (e.g., `ledger/tasks/withdraw.py`)
- Serializers in `market` and `financial` use dedicated directories
- Admin customization is extensive - check `admin.py` files for custom actions and list displays

## Deployment

The project uses GitLab CI/CD (`.gitlab-ci.yml`):
- **Branches**: `main`, `develop`, `release/gold`
- **Build stage**: Docker image build and push to registry
- **Deploy stage**: Automated deployment to Hamravesh/Darkube platform
- **Components**: API server, Celery beat scheduler, Celery workers
- Deployments are triggered automatically on push to tracked branches
