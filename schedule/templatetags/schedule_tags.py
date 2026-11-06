import os

from django import template
from django.contrib.staticfiles import finders
from django.templatetags.static import static

register = template.Library()


@register.simple_tag
def static_v(path):
    """{% static %} のURLに、ファイルを更新した時刻をつける（?v=...）。
    CSSを変えたときに、ブラウザに古いCSSが残って見た目が変わらない、ということがないように"""
    url = static(path)
    found = finders.find(path)
    if found:
        url += f'?v={int(os.path.getmtime(found))}'
    return url
