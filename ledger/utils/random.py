import os
from uuid import UUID


def secure_uuid4():
    return UUID(bytes=os.urandom(16), version=4)
