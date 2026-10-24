"""Persian admin for the menu and site settings.

Made for a non-technical owner who often works from a phone:

* prices are typed as plain text ("۲۵۰٬۰۰۰", "250,000", "250000") and checked
  against a sane range, so "18,000" can never silently become 18 Toman;
* slugs, stock photos and sort order live in a collapsed "advanced" section and
  slugs are generated automatically when left empty;
* success messages use Persian digits.
"""

import datetime
import re
from functools import lru_cache
from pathlib import Path

from django import forms
from django.apps import apps
from django.contrib import admin, messages
from django.db.models import Count, Q
from django.http import HttpResponseRedirect
from django.urls import reverse
from django.utils import timezone
from django.utils.html import format_html, format_html_join
from django.utils.safestring import SafeData, mark_safe
from django.utils.text import slugify

from .jalali import format_jalali, persian_digits
from .models import MAX_PRICE, MENU_PHOTO_DIR, MIN_PRICE, Category, MenuItem, MenuItemVariant, SiteSettings
from .templatetags.saray import fa_digits, price_short, toman
from .utils import ascii_digits, group_thousands

admin.site.site_header = 'پنل مدیریت رستوران سارای'
admin.site.site_title = 'سارای'
admin.site.index_title = 'مدیریت'
admin.site.site_url = '/'

ADVANCED = 'تنظیمات پیشرفته'


# --------------------------------------------------------------------------
# Shared helpers
# --------------------------------------------------------------------------

_TAG_SPLIT = re.compile(r'(<[^>]*>)')


def persian_digits_html(message):
    """Persian digits in the text of ``message`` but not inside HTML tags (links keep their URLs)."""
    text = str(message)
    converted = ''.join(
        part if part.startswith('<') else persian_digits(part) for part in _TAG_SPLIT.split(text)
    )
    return mark_safe(converted) if isinstance(message, SafeData) else converted


class PersianMessagesMixin:
    """Show Django's own success messages ("2 مورد ذخیره شد") with Persian digits."""

    def message_user(self, request, message, *args, **kwargs):
        return super().message_user(request, persian_digits_html(message), *args, **kwargs)


def ltr_input(**attrs):
    """Text input for numbers, phone numbers and links, which read left-to-right."""
    return forms.TextInput(attrs={'dir': 'ltr', 'class': 'sr-ltr', **attrs})


def jalali_datetime(value):
    """``۳۰ مهر ۱۴۰۵، ساعت ۲۰:۱۵`` in the restaurant's local time (no seconds)."""
    if not value:
        return '—'
    local = timezone.localtime(value)
    return f'{format_jalali(local.date(), long=True)}، ساعت {persian_digits(f"{local:%H:%M}")}'


# --------------------------------------------------------------------------
# Prices
# --------------------------------------------------------------------------

PRICE_MIN = MIN_PRICE
PRICE_MAX = MAX_PRICE
PRICE_HELP = 'به تومان، مثلاً ۲۵۰۰۰۰ (می‌توانید ۲۵۰٬۰۰۰ هم بنویسید).'
# Thousands separators people type: comma, Persian/Arabic separators, spaces.
_PRICE_SEPARATORS = re.compile(r'[\s,٬،‌‎‏  \']')
PRICE_ERRORS = {
    'required': 'لطفاً قیمت را وارد کنید.',
    'invalid': 'قیمت را فقط با عدد و به تومان بنویسید؛ مثلاً ۲۵۰۰۰۰ یا ۲۵۰٬۰۰۰.',
    'min_value': 'قیمت باید دست‌کم ۱٬۰۰۰ تومان باشد.',
    'too_small_hint': 'قیمت باید دست‌کم ۱٬۰۰۰ تومان باشد. منظورتان {} تومان بود؟',
    'max_value': 'قیمت نمی‌تواند بیشتر از ۱۰۰٬۰۰۰٬۰۰۰ تومان باشد.',
}


class PriceInput(forms.TextInput):
    """Left-to-right numeric text input that shows ``250,000`` for readability."""

    def __init__(self, attrs=None):
        base = {
            'inputmode': 'numeric', 'dir': 'ltr', 'autocomplete': 'off',
            'class': 'sr-price', 'size': '11', 'spellcheck': 'false',
        }
        super().__init__({**base, **(attrs or {})})

    def format_value(self, value):
        if isinstance(value, int):
            return f'{value:,}'
        return super().format_value(value)


class PriceField(forms.Field):
    """Toman price typed as text; accepts Persian digits and thousands separators."""

    widget = PriceInput
    default_error_messages = PRICE_ERRORS

    def __init__(self, *, required=True, **kwargs):
        kwargs.setdefault('help_text', PRICE_HELP)
        super().__init__(required=required, **kwargs)

    def to_python(self, value):
        if value in self.empty_values:
            return None
        if isinstance(value, int):
            return value
        text = _PRICE_SEPARATORS.sub('', ascii_digits(value))
        text = text.removesuffix('تومان')
        if text in self.empty_values:
            return None
        if not text.isascii() or not text.isdigit():
            raise forms.ValidationError(self.error_messages['invalid'], code='invalid')
        return int(text)

    def validate(self, value):
        super().validate(value)
        if value is None:
            return
        if value < PRICE_MIN:
            if 1 <= value * 1000 <= PRICE_MAX:
                raise forms.ValidationError(
                    self.error_messages['too_small_hint'].format(group_thousands(value * 1000)),
                    code='min_value',
                )
            raise forms.ValidationError(self.error_messages['min_value'], code='min_value')
        if value > PRICE_MAX:
            raise forms.ValidationError(self.error_messages['max_value'], code='max_value')

    def has_changed(self, initial, data):
        try:
            return self.to_python(initial) != self.to_python(data)
        except forms.ValidationError:
            return True


class PriceFieldMixin:
    """Use :class:`PriceField` for every ``price`` column (forms, list_editable, inlines)."""

    def formfield_for_dbfield(self, db_field, request, **kwargs):
        if db_field.name == 'price':
            return PriceField(
                required=not db_field.null,
                label=db_field.verbose_name,
                help_text=db_field.help_text or PRICE_HELP,
            )
        return super().formfield_for_dbfield(db_field, request, **kwargs)


# --------------------------------------------------------------------------
# Slugs and stock photos
# --------------------------------------------------------------------------


def unique_slug(model, base, exclude_pk=None, fallback='item'):
    """A slug for ``model`` that is not used by any other row (``kabab``, ``kabab-2``, …)."""
    max_length = model._meta.get_field('slug').max_length
    base = (base or '').strip('-')[: max_length - 4].strip('-')
    if not base:
        next_id = (model.objects.order_by('-pk').values_list('pk', flat=True).first() or 0) + 1
        base = f'{fallback}-{next_id}'
    others = model.objects.exclude(pk=exclude_pk) if exclude_pk else model.objects.all()
    candidate, n = base, 2
    while others.filter(slug=candidate).exists():
        candidate = f'{base}-{n}'
        n += 1
    return candidate


def slug_source(name_en, name):
    """English name if given (``kabab-koobideh``), else the Persian name (``کباب-کوبیده``)."""
    return slugify(name_en or '') or slugify(name or '', allow_unicode=True)


@lru_cache(maxsize=1)
def _stock_photo_keys_cached(mtime):
    folder = Path(apps.get_app_config('saray_menu').path) / 'static' / MENU_PHOTO_DIR
    if not folder.is_dir():
        return ()
    return tuple(sorted(
        p.stem for p in folder.glob('*.webp') if not p.stem.endswith('-sm')
    ))


def stock_photo_keys():
    """Names of the stock photos shipped in ``static/saray_menu/img/menu`` (without ``-sm``)."""
    folder = Path(apps.get_app_config('saray_menu').path) / 'static' / MENU_PHOTO_DIR
    try:
        mtime = folder.stat().st_mtime
    except OSError:
        return ()
    return _stock_photo_keys_cached(mtime)


def stock_photo_choices(current=''):
    choices = [('', '— بدون عکس پیش‌فرض —')] + [(key, key) for key in stock_photo_keys()]
    if current and current not in stock_photo_keys():
        choices.append((current, f'{current} (فایل این عکس پیدا نشد)'))
    return choices


class SlugAutoForm(forms.ModelForm):
    """Slug is optional: left empty, it is generated from the English or Persian name.

    Also used by inlines whose form has no slug field at all.
    """

    slug_fallback = 'item'

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if 'slug' in self.fields:
            old = self.fields['slug']
            self.fields['slug'] = forms.SlugField(
                label=old.label, max_length=old.max_length, required=False, allow_unicode=True,
                widget=ltr_input(),
                help_text='بخشی از نشانی صفحه. خالی بگذارید تا خودکار ساخته شود.',
                error_messages={'invalid': 'نامک فقط می‌تواند حرف، عدد، خط تیره (-) و زیرخط (_) داشته باشد.'},
            )
        if 'stock_photo' in self.fields:
            current = getattr(self.instance, 'stock_photo', '') or ''
            self.fields['stock_photo'] = forms.ChoiceField(
                label='عکس پیش‌فرض', required=False, choices=stock_photo_choices(current),
                help_text='یکی از عکس‌های آمادهٔ سایت؛ فقط وقتی استفاده می‌شود که تصویری آپلود نکرده باشید.',
            )

    def clean_slug(self):
        slug = (self.cleaned_data.get('slug') or '').strip()
        if slug:
            others = self._meta.model.objects.filter(slug=slug)
            if self.instance.pk:
                others = others.exclude(pk=self.instance.pk)
            if others.exists():
                raise forms.ValidationError('این نامک قبلاً برای مورد دیگری استفاده شده است.', code='unique')
        return slug

    def _get_validation_exclusions(self):
        # The slug may be Persian (unicode) and its uniqueness is checked in clean_slug().
        exclude = super()._get_validation_exclusions()
        exclude.add('slug')
        return exclude

    def _post_clean(self):
        super()._post_clean()
        instance = self.instance
        if not instance.slug and not self.errors:
            instance.slug = unique_slug(
                type(instance), slug_source(getattr(instance, 'name_en', ''), instance.name),
                exclude_pk=instance.pk, fallback=self.slug_fallback,
            )


class CategoryForm(SlugAutoForm):
    slug_fallback = 'category'

    class Meta:
        model = Category
        fields = '__all__'


class MenuItemForm(SlugAutoForm):
    class Meta:
        model = MenuItem
        fields = '__all__'


# --------------------------------------------------------------------------
# Thumbnails and previews
# --------------------------------------------------------------------------


def _thumb(obj, size=(64, 48)):
    return format_html(
        '<img src="{}" alt="" width="{}" height="{}" class="sr-thumb" loading="lazy" decoding="async">',
        obj.photo_sm_url, *size,
    )


def _preview(obj):
    if obj is None or not obj.pk:
        return '—'
    source = 'تصویر آپلودشده' if obj.image else ('عکس پیش‌فرض' if obj.stock_photo else 'تصویر جایگزین')
    return format_html(
        '<img src="{}" alt="" class="sr-preview" width="320" height="240"><div class="sr-help">{}</div>',
        obj.photo_url, source,
    )


class PhotoFilter(admin.SimpleListFilter):
    title = 'عکس'
    parameter_name = 'photo'

    def lookups(self, request, model_admin):
        return (
            ('uploaded', 'عکس آپلودشده'),
            ('stock', 'عکس پیش‌فرض سایت'),
            ('none', 'بدون عکس'),
        )

    def queryset(self, request, queryset):
        match self.value():
            case 'uploaded':
                return queryset.exclude(image='')
            case 'stock':
                return queryset.filter(image='').exclude(stock_photo='')
            case 'none':
                return queryset.filter(image='', stock_photo='')
        return queryset


# --------------------------------------------------------------------------
# Site settings (singleton)
# --------------------------------------------------------------------------


def _half_hours(extra=()):
    """00:00, 00:30 … 23:30 plus 23:59 (midnight) and any ``extra`` times."""
    times = {datetime.time(h, m) for h in range(24) for m in (0, 30)}
    times.add(datetime.time(23, 59))
    times.update(t.replace(second=0, microsecond=0) for t in extra if t)
    return sorted(times)


def _time_label(value):
    label = persian_digits(f'{value:%H:%M}')
    if value == datetime.time(23, 59):
        return f'{label} (نیمه‌شب)'
    return label


class TimeSelectField(forms.TypedChoiceField):
    """Pick a time from a list of HH:MM values (no seconds, no clock pop-up)."""

    def __init__(self, *, times, **kwargs):
        super().__init__(
            choices=[(f'{t:%H:%M}', _time_label(t)) for t in times],
            coerce=lambda v: datetime.datetime.strptime(v, '%H:%M').time(),
            **kwargs,
        )

    def prepare_value(self, value):
        if isinstance(value, datetime.time):
            return f'{value:%H:%M}'
        return value


SITE_HELP = {
    'phone': 'فقط برای دکمهٔ «تماس» استفاده می‌شود و روی سایت دیده نمی‌شود. به شکل بین‌المللی، '
             'مثل +984136688554.',
    'phone_display': 'همان شماره، به شکلی که روی سایت نوشته می‌شود؛ مثل ۰۴۱-۳۶۶۸۸۵۵۴. '
                     'اگر شماره عوض شد، هر دو فیلد تلفن را تغییر دهید.',
    'opening_hours_text': 'فقط متنی است که در سایت نمایش داده می‌شود (مثل «همه‌روزه از ۱۰ صبح تا ۱۲ شب»). '
                          'اگر ساعت کار عوض شد، دو فیلد ساعت پایین را هم تغییر دهید.',
    'opens_at': 'برچسب «باز است / بسته است» و جدول ساعات کاری سایت از این ساعت حساب می‌شوند.',
    'closes_at': '۲۳:۵۹ یعنی نیمه‌شب. برچسب «باز است / بسته است» از این ساعت حساب می‌شود.',
    'latitude': 'اختیاری؛ برای نقشهٔ سایت. مثل 38.0667',
    'longitude': 'اختیاری؛ برای نقشهٔ سایت. مثل 46.3000',
}


@admin.register(SiteSettings)
class SiteSettingsAdmin(PersianMessagesMixin, admin.ModelAdmin):
    fieldsets = (
        ('معرفی', {'fields': ('name', 'tagline', 'about_text', 'announcement')}),
        ('تماس و نشانی', {'fields': ('phone_display', 'phone', 'address', 'map_url', ('latitude', 'longitude'))}),
        ('ساعات کاری', {'fields': ('opening_hours_text', ('opens_at', 'closes_at'))}),
        ('شبکه‌های اجتماعی', {'fields': ('instagram_url', 'telegram_url')}),
        ('رزرو آنلاین', {'fields': ('reservations_enabled',)}),
    )

    def get_form(self, request, obj=None, change=False, **kwargs):
        form = super().get_form(request, obj, change, **kwargs)
        fields = form.base_fields
        for name, text in SITE_HELP.items():
            if name in fields:
                fields[name].help_text = text
        ltr = {'dir': 'ltr', 'class': 'sr-ltr'}
        if 'phone' in fields:
            fields['phone'].widget = forms.TextInput(attrs={**ltr, 'inputmode': 'tel'})
        for name in ('latitude', 'longitude'):
            if name in fields:
                fields[name].widget = forms.TextInput(attrs={**ltr, 'inputmode': 'decimal'})
        for name in ('map_url', 'instagram_url', 'telegram_url'):
            if name in fields:
                fields[name].widget = forms.URLInput(attrs={**ltr, 'placeholder': 'https://', 'class': 'vURLField sr-ltr'})
        for name in ('opens_at', 'closes_at'):
            if name in fields:
                current = getattr(obj, name, None)
                old = fields[name]
                fields[name] = TimeSelectField(
                    times=_half_hours([current] if current else []),
                    label=old.label, help_text=old.help_text, required=old.required,
                )
        return form

    def has_add_permission(self, request):
        return not SiteSettings.objects.exists()

    def has_delete_permission(self, request, obj=None):
        return False

    def changelist_view(self, request, extra_context=None):
        """There is only one settings row: go straight to its edit page."""
        obj = SiteSettings.load()
        return HttpResponseRedirect(reverse('admin:saray_menu_sitesettings_change', args=[obj.pk]))


# --------------------------------------------------------------------------
# Categories
# --------------------------------------------------------------------------


class MenuItemInline(PriceFieldMixin, admin.TabularInline):
    model = MenuItem
    form = MenuItemForm
    fields = ('name', 'price', 'is_available', 'is_featured', 'order')
    extra = 0
    show_change_link = True
    ordering = ('order', 'id')
    verbose_name = 'غذا'
    verbose_name_plural = 'غذاهای این دسته'


@admin.register(Category)
class CategoryAdmin(PersianMessagesMixin, admin.ModelAdmin):
    form = CategoryForm
    list_display = ('thumbnail', 'name', 'icon', 'items_total', 'items_available', 'order', 'is_active')
    list_display_links = ('thumbnail', 'name')
    list_editable = ('order', 'is_active')
    list_filter = ('is_active', 'icon')
    search_fields = ('name', 'name_en', 'slug')
    prepopulated_fields = {'slug': ('name_en',)}
    readonly_fields = ('image_preview',)
    inlines = [MenuItemInline]
    fieldsets = (
        (None, {'fields': ('name', 'description', 'icon', 'is_active')}),
        ('تصویر', {'fields': ('image', 'image_preview')}),
        (ADVANCED, {
            'fields': ('name_en', 'slug', 'stock_photo', 'order'),
            'classes': ('collapse',),
            'description': 'معمولاً لازم نیست این‌ها را تغییر دهید. نامک اگر خالی بماند خودکار ساخته می‌شود؛ '
                           'دسته‌ها به ترتیب عدد «ترتیب» (کوچک‌تر اول) نمایش داده می‌شوند.',
        }),
    )

    def get_queryset(self, request):
        return super().get_queryset(request).annotate(
            _items_total=Count('items', distinct=True),
            _items_available=Count('items', filter=Q(items__is_available=True), distinct=True),
        )

    @admin.display(description='تصویر')
    def thumbnail(self, obj):
        return _thumb(obj)

    @admin.display(description='تعداد غذا', ordering='_items_total')
    def items_total(self, obj):
        return fa_digits(obj._items_total)

    @admin.display(description='موجود', ordering='_items_available')
    def items_available(self, obj):
        return fa_digits(obj._items_available)

    @admin.display(description='پیش‌نمایش تصویر')
    def image_preview(self, obj):
        return _preview(obj)


# --------------------------------------------------------------------------
# Menu items
# --------------------------------------------------------------------------


class MenuItemVariantInline(PriceFieldMixin, admin.TabularInline):
    model = MenuItemVariant
    fields = ('label', 'price', 'order')
    extra = 0


@admin.register(MenuItem)
class MenuItemAdmin(PriceFieldMixin, PersianMessagesMixin, admin.ModelAdmin):
    form = MenuItemForm
    list_display = (
        'thumbnail', 'name', 'category', 'price', 'price_display',
        'is_available', 'is_featured', 'flags',
    )
    list_display_links = ('thumbnail', 'name')
    list_editable = ('price', 'is_available', 'is_featured')
    list_filter = ('category', 'is_available', 'is_featured', PhotoFilter, 'is_spicy', 'is_vegetarian')
    list_select_related = ('category',)
    search_fields = ('name', 'name_en', 'description', 'slug')
    prepopulated_fields = {'slug': ('name_en',)}
    readonly_fields = ('image_preview', 'created_display', 'updated_display')
    inlines = [MenuItemVariantInline]
    list_per_page = 50
    save_on_top = True
    actions = ('make_unavailable', 'make_available', 'make_featured', 'make_not_featured')
    fieldsets = (
        (None, {'fields': ('category', 'name', 'description')}),
        ('قیمت', {
            'fields': ('price',),
            'description': 'برای غذاهایی که چند اندازه دارند (مثل پیتزا) قیمت را خالی بگذارید و '
                           'اندازه‌ها را در جدول پایین وارد کنید.',
        }),
        ('نمایش', {'fields': (('is_available', 'is_featured'), ('is_spicy', 'is_vegetarian'))}),
        ('تصویر', {'fields': ('image', 'image_preview')}),
        (ADVANCED, {
            'fields': ('name_en', 'slug', 'stock_photo', 'order'),
            'classes': ('collapse',),
            'description': 'معمولاً لازم نیست این‌ها را تغییر دهید. نامک اگر خالی بماند خودکار ساخته می‌شود؛ '
                           'غذاها در هر دسته به ترتیب عدد «ترتیب» (کوچک‌تر اول) نمایش داده می‌شوند.',
        }),
        ('سوابق', {'fields': ('created_display', 'updated_display'), 'classes': ('collapse',)}),
    )

    def get_queryset(self, request):
        return super().get_queryset(request).prefetch_related('variants')

    @admin.display(description='تصویر')
    def thumbnail(self, obj):
        return _thumb(obj)

    @admin.display(description='قیمت روی سایت', ordering='price')
    def price_display(self, obj):
        if obj.price is not None:
            return toman(obj.price)
        variants = list(obj.variants.all())
        if variants:
            return ' / '.join(price_short(v.price) for v in variants) + ' هزار تومان'
        return format_html('<span class="sr-muted">{}</span>', 'بدون قیمت')

    @admin.display(description='ویژگی‌ها')
    def flags(self, obj):
        badges = []
        if obj.is_spicy:
            badges.append(('sr-flag sr-flag--spicy', 'تند'))
        if obj.is_vegetarian:
            badges.append(('sr-flag sr-flag--veg', 'گیاهی'))
        if not badges:
            return ''
        return format_html_join(' ', '<span class="{}">{}</span>', badges)

    @admin.display(description='پیش‌نمایش تصویر')
    def image_preview(self, obj):
        return _preview(obj)

    @admin.display(description='تاریخ ایجاد')
    def created_display(self, obj):
        return jalali_datetime(obj.created_at)

    @admin.display(description='آخرین ویرایش')
    def updated_display(self, obj):
        return jalali_datetime(obj.updated_at)

    def _bulk_update(self, request, queryset, message, **values):
        count = queryset.update(updated_at=timezone.now(), **values)
        self.message_user(request, message.format(fa_digits(count)), messages.SUCCESS)

    @admin.action(description='ناموجود کردن غذاهای انتخاب‌شده')
    def make_unavailable(self, request, queryset):
        self._bulk_update(request, queryset, '{} غذا ناموجود شد.', is_available=False)

    @admin.action(description='موجود کردن غذاهای انتخاب‌شده')
    def make_available(self, request, queryset):
        self._bulk_update(request, queryset, '{} غذا موجود شد.', is_available=True)

    @admin.action(description='افزودن به پیشنهاد سرآشپز')
    def make_featured(self, request, queryset):
        self._bulk_update(request, queryset, '{} غذا به پیشنهادها اضافه شد.', is_featured=True)

    @admin.action(description='حذف از پیشنهاد سرآشپز')
    def make_not_featured(self, request, queryset):
        self._bulk_update(request, queryset, '{} غذا از پیشنهادها حذف شد.', is_featured=False)
