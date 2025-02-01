from accounts.utils.melipayamak.rest import Rest


class MeliPayamak:
    def __init__(self, username, password, number):
        self.username = username
        self.password = password
        self.number = number

    def sms(self, _method="rest", _type=""):
        return Rest(self.username, self.password, self.number)
