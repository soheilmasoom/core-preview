from accounts.utils.melipayamak.rest import Rest


class MeliPayamak:
    def __init__(self, username, password):
        self.username = username
        self.password = password

    def sms(self, _method="rest", _type=""):
        return Rest(self.username, self.password)
