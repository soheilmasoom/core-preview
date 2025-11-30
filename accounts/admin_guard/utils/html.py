from typing import List


def get_table_html(headers: list, data: List[dict]):
    headers = [(h, h) if not isinstance(h, tuple) else h for h in headers]

    header_html = ''.join(map(lambda h: f"<th style='text-align: left'>{h[1]}</th>", headers))

    body_html = ""
    for row in data:
        row_html = ''.join(map(lambda h: f"<td>{row.get(h[0], '')}</td>", headers))
        body_html += f"<tr>{row_html}</tr>"

    html = f'<table dir="ltr"><thead><tr>{header_html}</tr></thead><tbody>{body_html}</tbody></table>'

    return html
