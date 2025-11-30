from decouple import config
from redis.client import Redis


if __name__ == '__main__':
    socket_server_redis = Redis.from_url(config('SOCKET_SERVER_CACHE_LOCATION',  default='redis://127.0.0.1:6379'), decode_responses=True)

    if not socket_server_redis.get('market_depth_snapshot_liveness'):
        print("Error...")
    else:
        print("OK!")
