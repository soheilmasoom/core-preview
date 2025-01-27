def add_commas_to_number(number):
    persian_digits = str(number).translate(str.maketrans("0123456789", "۰۱۲۳۴۵۶۷۸۹"))
    parts = persian_digits.split(".")
    parts[0] = "{:,}".format(int(parts[0])).replace(",", "٬").translate(str.maketrans("0123456789", "۰۱۲۳۴۵۶۷۸۹"))
    return "٫".join(parts)
