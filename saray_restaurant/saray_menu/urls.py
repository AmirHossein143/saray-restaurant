from django.urls import path
from django.views.generic import RedirectView

from . import views

urlpatterns = [
    path('', views.home, name='home'),
    path('menu/', views.menu, name='menu'),
    path('about/', views.about, name='about'),
    path('contact/', views.contact, name='contact'),
    path('credits/', views.credits, name='credits'),
    path('robots.txt', views.robots_txt, name='robots_txt'),
]

# Old addresses (the first Django version under /saray-menu/ and the static
# HTML prototype) permanently redirect so bookmarks and search results work.
LEGACY_REDIRECTS = (
    ('saray-menu/', 'home'),
    ('saray-menu/menu/', 'menu'),
    ('index.html', 'home'),
    ('saray.html', 'home'),
    ('menu.html', 'menu'),
    ('blog.html', 'home'),
)
urlpatterns += [
    path(old, RedirectView.as_view(pattern_name=name, permanent=True, query_string=True))
    for old, name in LEGACY_REDIRECTS
]
