from django.conf import settings


def site(request):
    """すべての画面で使う、研究室ごとの見た目（ロゴ・favicon・名前）"""
    return {
        'site_name': settings.SITE_NAME,
        'site_logo': settings.SITE_LOGO,
        'site_favicon': settings.SITE_FAVICON,
    }
