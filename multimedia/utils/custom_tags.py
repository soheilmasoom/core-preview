import re

from bs4 import BeautifulSoup


VIDEO_REGEX = re.compile(r'VIDEO\s+([^ ]+)\s+([^ ]+)')
REPLACE_WITH = '<video style="width: 100%" controls poster="{1}"><source src="{0}" type="video/mp4" />مرورگر شما قابلیت نمایش ویدیو را ندارد.</video>'

EMPTY_STYLE_REGEX = re.compile(r' style=\"\s*\"')


def parse_table(content: str):
    rows = list(filter(lambda x: x, content.split('\n')))[1:]
    header = ''.join(map(lambda h: f'<th>{h}</th>', rows[0].split('|')))
    body = ''

    for row in rows[1:]:
        b = ''.join(map(
            lambda item: f'<td>{item}</td>',
            row.split('|')
        ))
        body += f'<tr>{b}</tr>'

    return f'<table><thead><tr>{header}</tr></thead><tbody>{body}</tbody></table>'


def post_render_html(html: str) -> str:
    html = html.replace('color: rgb(0, 0, 0);', '').replace('background-color: transparent;', '').replace(' ', ' ')
    html = EMPTY_STYLE_REGEX.sub("", html)
    tree = BeautifulSoup(html, 'html.parser')
    for node in tree.findAll('pre'):
        content = node.text.strip()
        rgx = VIDEO_REGEX.match(content)

        inner_html = None

        if rgx:
            inner_html = REPLACE_WITH.format(*rgx.groups())

        elif content.startswith('TABLE'):
            inner_html = parse_table(content)

        if inner_html is not None:
            node.replaceWith(BeautifulSoup(inner_html, 'html.parser'))

    return str(tree)


def get_text_of_html(html: str) -> str:
    return BeautifulSoup(html, 'html.parser').get_text(' ')
