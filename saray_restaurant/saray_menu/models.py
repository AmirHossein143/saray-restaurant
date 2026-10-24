"""Menu and site-wide settings for the Saray restaurant."""

import datetime
from functools import lru_cache

from django.conf import settings
from django.contrib.staticfiles import finders
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models
from django.templatetags.static import static
from django.urls import reverse

PLACEHOLDER_PHOTO = 'saray_menu/img/ui/placeholder.webp'
MENU_PHOTO_DIR = 'saray_menu/img/menu'
# Sane price range in Toman (catches "18" typed for 18,000).
MIN_PRICE = 1_000
MAX_PRICE = 100_000_000

# Default content for the singleton SiteSettings row (also used by the seed
# data migration). Only facts supplied by the owner, plus atmospheric copy.
DEFAULT_NAME = 'رستوران سارای'
DEFAULT_TAGLINE = 'کباب زغالی و دستپخت اصیل ایرانی در قلب تبریز'
DEFAULT_PHONE = '+984136688554'
DEFAULT_PHONE_DISPLAY = '۰۴۱-۳۶۶۸۸۵۵۴'
DEFAULT_ADDRESS = 'تبریز، باغمیشه، روبروی بازار ماهی'
DEFAULT_OPENING_HOURS = 'همه‌روزه از ۱۰ صبح تا ۱۲ شب'
DEFAULT_ABOUT = (
    'سارای جایی است برای دورهمی‌های بی‌تکلف و شام‌هایی که در یاد می‌مانند. '
    'بوی کباب زغالی، عطر برنج زعفرانی و گرمای گفت‌وگوی سر میزها، حال‌وهوای '
    'یک رستوران خانوادگی تبریزی را می‌سازد.\n\n'
    'در آشپزخانهٔ ما کباب‌ها روی آتش زغال آماده می‌شوند و خورش‌ها با حوصله جا '
    'می‌افتند. کنار غذاهای اصیل ایرانی، پیتزا، پاستا و برگر هم برای '
    'سلیقه‌های گوناگون سر سفره است.\n\n'
    'چه برای یک ناهار دلچسب به باغمیشه آمده باشید و چه برای جشنی کوچک با '
    'خانواده و دوستان، با مهمان‌نوازی تبریزی منتظرتان هستیم.'
)


@lru_cache(maxsize=1024)
def _static_file_exists_cached(path):
    return bool(finders.find(path))


def static_file_exists(path):
    """True if a static file exists in any static source.

    Cached per process in production (files only change on deploy); never
    cached in DEBUG so photos added while runserver is running show up.
    """
    if settings.DEBUG:
        return bool(finders.find(path))
    return _static_file_exists_cached(path)


def _photo_url(instance, small=False):
    """Uploaded image → stock photo shipped in static → placeholder."""
    if instance.image:
        try:
            return instance.image.url
        except ValueError:
            pass
    if instance.stock_photo:
        path = f'{MENU_PHOTO_DIR}/{instance.stock_photo}{"-sm" if small else ""}.webp'
        if static_file_exists(path):
            return static(path)
        if small:
            full = f'{MENU_PHOTO_DIR}/{instance.stock_photo}.webp'
            if static_file_exists(full):
                return static(full)
    return static(PLACEHOLDER_PHOTO)


class SiteSettings(models.Model):
    """Singleton (pk=1) holding everything the owner can edit about the site."""

    name = models.CharField('نام رستوران', max_length=100, default=DEFAULT_NAME)
    tagline = models.CharField(
        'شعار', max_length=200, blank=True, default=DEFAULT_TAGLINE,
        help_text='یک جملهٔ کوتاه زیر نام رستوران در صفحهٔ اصلی.',
    )
    phone = models.CharField(
        'شماره تلفن (برای تماس)', max_length=20, default=DEFAULT_PHONE,
        help_text='به شکل بین‌المللی، مثل +984136688554 — برای لینک تماس استفاده می‌شود.',
    )
    phone_display = models.CharField(
        'شماره تلفن (نمایشی)', max_length=40, default=DEFAULT_PHONE_DISPLAY,
        help_text='همان‌طور که روی سایت نمایش داده می‌شود.',
    )
    address = models.CharField('نشانی', max_length=255, default=DEFAULT_ADDRESS)
    about_text = models.TextField(
        'متن درباره ما', blank=True, default=DEFAULT_ABOUT,
        help_text='پاراگراف‌ها را با یک خط خالی از هم جدا کنید.',
    )
    opening_hours_text = models.CharField(
        'ساعات کاری (متن)', max_length=120, default=DEFAULT_OPENING_HOURS,
    )
    opens_at = models.TimeField('ساعت شروع کار', default=datetime.time(10, 0))
    closes_at = models.TimeField(
        'ساعت پایان کار', default=datetime.time(23, 59),
        help_text='۲۳:۵۹ یعنی نیمه‌شب.',
    )
    instagram_url = models.URLField('نشانی اینستاگرام', blank=True)
    telegram_url = models.URLField('نشانی تلگرام', blank=True)
    map_url = models.URLField(
        'لینک نقشه', blank=True,
        help_text='لینک موقعیت رستوران در نشان، بلد یا گوگل‌مپ.',
    )
    latitude = models.DecimalField(
        'عرض جغرافیایی', max_digits=9, decimal_places=6, null=True, blank=True,
        validators=[MinValueValidator(-90), MaxValueValidator(90)],
    )
    longitude = models.DecimalField(
        'طول جغرافیایی', max_digits=9, decimal_places=6, null=True, blank=True,
        validators=[MinValueValidator(-180), MaxValueValidator(180)],
    )
    reservations_enabled = models.BooleanField(
        'رزرو آنلاین فعال است', default=True,
        help_text='اگر غیرفعال باشد، صفحهٔ رزرو فقط شماره تماس را نشان می‌دهد.',
    )
    announcement = models.CharField(
        'اطلاعیه', max_length=200, blank=True,
        help_text='در صورت پر بودن، به‌صورت نوار باریک بالای همهٔ صفحه‌ها نمایش داده می‌شود.',
    )

    class Meta:
        verbose_name = 'تنظیمات سایت'
        verbose_name_plural = 'تنظیمات سایت'

    def __str__(self):
        return self.name

    def save(self, *args, **kwargs):
        self.pk = 1
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        """The settings row cannot be deleted."""
        return 0, {}

    @classmethod
    def load(cls):
        obj, _ = cls.objects.get_or_create(pk=1)
        return obj

    @property
    def tel_href(self):
        return 'tel:' + ''.join(ch for ch in self.phone if ch.isdigit() or ch == '+')

    @property
    def has_location(self):
        return self.latitude is not None and self.longitude is not None

    @property
    def about_paragraphs(self):
        return [p.strip() for p in self.about_text.split('\n\n') if p.strip()]


class Category(models.Model):
    class Icon(models.TextChoices):
        SALAD = 'salad', 'سالاد / پیش‌غذا'
        SKEWER = 'skewer', 'سیخ کباب'
        POT = 'pot', 'دیگ / خورش'
        FLAME = 'flame', 'شعله / کبابی'
        PASTA = 'pasta', 'پاستا'
        PIZZA = 'pizza', 'پیتزا'
        BURGER = 'burger', 'برگر'
        DESSERT = 'dessert', 'دسر'
        CUP = 'cup', 'نوشیدنی'

    name = models.CharField('نام', max_length=100)
    name_en = models.CharField('نام انگلیسی', max_length=100, blank=True)
    slug = models.SlugField('نامک (slug)', max_length=100, unique=True, allow_unicode=False)
    description = models.TextField('توضیحات', blank=True)
    icon = models.CharField('آیکون', max_length=20, choices=Icon.choices, default=Icon.SKEWER)
    image = models.ImageField(
        'تصویر', upload_to='categories/', blank=True,
        help_text='اختیاری؛ اگر خالی باشد از عکس پیش‌فرض استفاده می‌شود. نسبت ۴:۳ پیشنهاد می‌شود.',
    )
    stock_photo = models.CharField('کلید عکس پیش‌فرض', max_length=100, blank=True)
    order = models.PositiveIntegerField('ترتیب', default=0)
    is_active = models.BooleanField('فعال', default=True)

    class Meta:
        ordering = ['order', 'id']
        verbose_name = 'دسته‌بندی'
        verbose_name_plural = 'دسته‌بندی‌ها'

    def __str__(self):
        return self.name

    def get_absolute_url(self):
        return f'{reverse("menu")}#{self.slug}'

    @property
    def photo_url(self):
        return _photo_url(self)

    @property
    def photo_sm_url(self):
        return _photo_url(self, small=True)


class MenuItem(models.Model):
    category = models.ForeignKey(
        Category, on_delete=models.CASCADE, related_name='items', verbose_name='دسته‌بندی',
    )
    name = models.CharField('نام', max_length=150)
    name_en = models.CharField('نام انگلیسی', max_length=150, blank=True)
    slug = models.SlugField('نامک (slug)', max_length=150, unique=True)
    description = models.TextField('توضیحات / مواد تشکیل‌دهنده', blank=True)
    price = models.PositiveIntegerField(
        'قیمت (تومان)', null=True, blank=True,
        validators=[
            MinValueValidator(MIN_PRICE, 'قیمت باید دست‌کم ۱٬۰۰۰ تومان باشد.'),
            MaxValueValidator(MAX_PRICE, 'قیمت نمی‌تواند بیشتر از ۱۰۰٬۰۰۰٬۰۰۰ تومان باشد.'),
        ],
        help_text='به تومان، مثلاً ۲۵۰۰۰۰. اگر غذا چند اندازه دارد یا قیمت ثابت ندارد، خالی بگذارید.',
    )
    image = models.ImageField(
        'تصویر', upload_to='menu/', blank=True,
        help_text='اختیاری؛ اگر خالی باشد از عکس پیش‌فرض استفاده می‌شود. نسبت ۴:۳ پیشنهاد می‌شود.',
    )
    stock_photo = models.CharField('کلید عکس پیش‌فرض', max_length=100, blank=True)
    is_available = models.BooleanField('موجود', default=True)
    is_featured = models.BooleanField('پیشنهاد سرآشپز', default=False)
    is_spicy = models.BooleanField('تند', default=False)
    is_vegetarian = models.BooleanField('گیاهی', default=False)
    order = models.PositiveIntegerField('ترتیب', default=0)
    created_at = models.DateTimeField('تاریخ ایجاد', auto_now_add=True)
    updated_at = models.DateTimeField('آخرین ویرایش', auto_now=True)

    class Meta:
        ordering = ['category__order', 'order', 'id']
        verbose_name = 'غذا'
        verbose_name_plural = 'غذاها'

    def __str__(self):
        return self.name

    def get_absolute_url(self):
        return self.category.get_absolute_url()

    @property
    def photo_url(self):
        return _photo_url(self)

    @property
    def photo_sm_url(self):
        return _photo_url(self, small=True)

    @property
    def min_price(self):
        """The item price, else the cheapest variant price, else ``None``."""
        if self.price is not None:
            return self.price
        prices = [v.price for v in self.variants.all() if v.price is not None]
        return min(prices) if prices else None


class MenuItemVariant(models.Model):
    item = models.ForeignKey(
        MenuItem, on_delete=models.CASCADE, related_name='variants', verbose_name='غذا',
    )
    label = models.CharField('عنوان', max_length=60, help_text='مثلاً «متوسط ۲۸ سانتی».')
    price = models.PositiveIntegerField(
        'قیمت (تومان)',
        validators=[
            MinValueValidator(MIN_PRICE, 'قیمت باید دست‌کم ۱٬۰۰۰ تومان باشد.'),
            MaxValueValidator(MAX_PRICE, 'قیمت نمی‌تواند بیشتر از ۱۰۰٬۰۰۰٬۰۰۰ تومان باشد.'),
        ],
        help_text='به تومان، مثلاً ۲۵۰۰۰۰',
    )
    order = models.PositiveIntegerField('ترتیب', default=0)

    class Meta:
        ordering = ['order', 'id']
        verbose_name = 'اندازه / نوع'
        verbose_name_plural = 'اندازه‌ها / انواع'
        constraints = [
            models.UniqueConstraint(fields=['item', 'label'], name='unique_variant_label_per_item'),
        ]

    def __str__(self):
        return f'{self.item.name} — {self.label}'
