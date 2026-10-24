"""Root URL configuration for the Saray website."""

from django.conf import settings
from django.contrib import admin
from django.contrib.sitemaps.views import sitemap
from django.urls import include, path, re_path
from django.views.static import serve

from saray_menu.sitemaps import sitemaps

urlpatterns = [
    path('admin/', admin.site.urls),
    path('studio/', include('studio.urls')),
    path('reserve/', include('reservations.urls')),
    path('sitemap.xml', sitemap, {'sitemaps': sitemaps}, name='sitemap'),
    path('', include('saray_menu.urls')),
]

if settings.SERVE_MEDIA:
    urlpatterns += [
        re_path(
            r'^%s(?P<path>.*)$' % settings.MEDIA_URL.lstrip('/'),
            serve,
            {'document_root': settings.MEDIA_ROOT},
        ),
    ]

handler404 = 'saray_menu.views.page_not_found'
handler500 = 'saray_menu.views.server_error'
