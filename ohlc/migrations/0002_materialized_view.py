from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [
        ('ohlc', '0001_initial'),
    ]

    operations = [
        migrations.RunSQL(
            """
            CREATE MATERIALIZED VIEW ohlc_1h AS
            SELECT
                ROW_NUMBER() OVER (ORDER BY symbol, date_trunc('hour', timestamp)) AS row_id,
                symbol,
                date_trunc('hour', timestamp) AS timestamp,
                (ARRAY_AGG(open ORDER BY timestamp ASC))[1] AS open,  -- First value
                MAX(high) AS high,
                MIN(low) AS low,
                (ARRAY_AGG(close ORDER BY timestamp DESC))[1] AS close, -- Last value
                SUM(volume) AS volume
            FROM ohlc_candle
            GROUP BY
                symbol, date_trunc('hour', timestamp)
            WITH DATA;

            CREATE UNIQUE INDEX ohlc_1h_pkey ON ohlc_1h (row_id);
            CREATE INDEX idx_ohlc_1h_symbol ON ohlc_1h (symbol);
            CREATE INDEX idx_ohlc_1h_timestamp ON ohlc_1h (timestamp);
            """,
            reverse_sql="""
            DROP MATERIALIZED VIEW IF EXISTS ohlc_1h CASCADE;
            """
        ),
        migrations.RunSQL(
            """
            CREATE MATERIALIZED VIEW ohlc_1d AS
            SELECT
                ROW_NUMBER() OVER (ORDER BY symbol, date_trunc('day', timestamp)) AS row_id,
                symbol,
                date_trunc('day', timestamp) AS timestamp,
                (ARRAY_AGG(open ORDER BY timestamp ASC))[1] AS open,  -- First value
                MAX(high) AS high,
                MIN(low) AS low,
                (ARRAY_AGG(close ORDER BY timestamp DESC))[1] AS close, -- Last value
                SUM(volume) AS volume
            FROM ohlc_candle
            GROUP BY
                symbol, date_trunc('day', timestamp)
            WITH DATA;

            CREATE UNIQUE INDEX ohlc_1d_pkey ON ohlc_1d (row_id);
            CREATE INDEX idx_ohlc_1d_symbol ON ohlc_1d (symbol);
            CREATE INDEX idx_ohlc_1d_timestamp ON ohlc_1d (timestamp);
            """,
            reverse_sql="""
            DROP MATERIALIZED VIEW IF EXISTS ohlc_1d CASCADE;
            """
        ),
    ]
