from django.contrib.sitemaps import Sitemap
from django.db.models import Max
from django.urls import reverse

from .models import MenuItem


class StaticViewSitemap(Sitemap):
    """Public pages that rarely change."""

    pages = {
        'home': (1.0, 'weekly'),
        'about': (0.6, 'monthly'),
        'contact': (0.7, 'monthly'),
        'reservations:create': (0.7, 'monthly'),
        'credits': (0.2, 'yearly'),
    }

    def items(self):
        return list(self.pages)

    def location(self, item):
        return reverse(item)

    def priority(self, item):
        return self.pages[item][0]

    def changefreq(self, item):
        return self.pages[item][1]


class MenuSitemap(Sitemap):
    """The menu page; ``lastmod`` is the most recent dish edit."""

    priority = 0.9
    changefreq = 'weekly'

    def items(self):
        return ['menu']

    def location(self, item):
        return reverse(item)

    def lastmod(self, item):
        return MenuItem.objects.aggregate(latest=Max('updated_at'))['latest']


sitemaps = {'static': StaticViewSitemap, 'menu': MenuSitemap}
