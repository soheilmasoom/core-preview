
# Development
## env
```ln -s .env.development .env```


# Deployment
## RSA Keypair

### generate a private key with the correct length
```openssl genrsa -out private-key.pem 3072```

### generate corresponding public key
```openssl rsa -in private-key.pem -pubout -out public-key.pem```

# DB
### Config Metabase
```postgresql
\c mydb
CREATE ROLE metabase;
ALTER ROLE metabase WITH PASSWORD 'password' LOGIN;
GRANT CONNECT ON DATABASE core_db TO metabase;
GRANT USAGE ON SCHEMA public TO metabase;
GRANT SELECT ON ALL TABLES IN SCHEMA public TO metabase;
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT SELECT ON TABLES TO metabase;

-- if needed to exclude some
REVOKE SELECT ON accounts_user from metabase;
REVOKE SELECT ON accounts_historicaluser from metabase;
REVOKE SELECT ON accounts_user from metabase;
REVOKE SELECT ON django_session from metabase;
REVOKE SELECT ON otp_totp_totpdevice from metabase;
REVOKE SELECT ON accounts_customtoken FROM metabase;

CREATE VIEW accounts_users AS SELECT id, last_login, is_superuser, username, first_name, last_name, email, is_staff, 
                                     is_active, date_joined, phone, birth_date, birth_date_verified, first_name_verified, 
                                     last_name_verified, level, national_code, national_code_verified, verify_status, 
                                     first_fiat_deposit_date, first_crypto_deposit_date, level_2_verify_datetime, 
                                     level_3_verify_datetime, archived, margin_quiz_pass_date, show_margin, 
                                     show_strategy_bot, show_community, show_staking, can_withdraw, can_trade, promotion 
FROM accounts_user;

CREATE VIEW accounts_historicalusers AS SELECT history_id, history_date, history_change_reason, history_type, history_user_id,
                                     id, last_login, is_superuser, username, first_name, last_name, email, is_staff, 
                                     is_active, date_joined, phone, birth_date, birth_date_verified, first_name_verified, 
                                     last_name_verified, level, national_code, national_code_verified, verify_status, 
                                     first_fiat_deposit_date, first_crypto_deposit_date, level_2_verify_datetime, 
                                     level_3_verify_datetime, archived, margin_quiz_pass_date, show_margin, 
                                     show_strategy_bot, show_community, show_staking, can_withdraw, can_trade, promotion 
FROM accounts_historicaluser;

GRANT SELECT ON accounts_users TO metabase;
GRANT SELECT ON accounts_historicalusers TO metabase;
```

# Rabbitmq
```shell
rabbitmqctl add_vhost my_vhost
rabbitmqctl set_permissions -p my_vhost rabbitmq ".*" ".*" ".*"
```


# Elasticmail
to upload a file see [here](https://api.elasticemail.com/public/help/legacy#File_Upload)
using ```https://restfox.dev/```


# Firebase
get firebase json 
[from](https://console.cloud.google.com/iam-admin/serviceaccounts/details/105627163563818169274/permissions)
