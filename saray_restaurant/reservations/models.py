"""Table reservations."""

import secrets

from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import IntegrityError, models, transaction

# No 0/O/1/I so codes can be read over the phone without confusion.
CODE_ALPHABET = 'ABCDEFGHJKLMNPQRSTUVWXYZ23456789'
CODE_LENGTH = 6
CODE_ATTEMPTS = 5
MIN_GUESTS = 1
MAX_GUESTS = 20


def generate_code():
    return ''.join(secrets.choice(CODE_ALPHABET) for _ in range(CODE_LENGTH))


class Reservation(models.Model):
    class Occasion(models.TextChoices):
        NONE = '', 'بدون مناسبت خاص'
        BIRTHDAY = 'birthday', 'تولد'
        ANNIVERSARY = 'anniversary', 'سالگرد'
        BUSINESS = 'business', 'کاری'
        OTHER = 'other', 'سایر'

    class Status(models.TextChoices):
        PENDING = 'pending', 'در انتظار تایید'
        CONFIRMED = 'confirmed', 'تایید شده'
        SEATED = 'seated', 'حاضر شد'
        CANCELLED = 'cancelled', 'لغو شده'
        NO_SHOW = 'no_show', 'نیامد'

    code = models.CharField('کد رزرو', max_length=CODE_LENGTH, unique=True, editable=False)
    name = models.CharField('نام و نام خانوادگی', max_length=100)
    phone = models.CharField('شماره تماس', max_length=15)
    date = models.DateField('تاریخ')
    time = models.TimeField('ساعت')
    guests = models.PositiveSmallIntegerField(
        'تعداد نفرات',
        validators=[MinValueValidator(MIN_GUESTS), MaxValueValidator(MAX_GUESTS)],
    )
    occasion = models.CharField(
        'مناسبت', max_length=20, choices=Occasion.choices, blank=True, default='',
    )
    notes = models.TextField('توضیحات مهمان', max_length=500, blank=True)
    status = models.CharField(
        'وضعیت', max_length=20, choices=Status.choices, default=Status.PENDING, db_index=True,
    )
    staff_note = models.TextField('یادداشت داخلی', blank=True, help_text='فقط برای کارکنان.')
    created_at = models.DateTimeField('زمان ثبت', auto_now_add=True)
    updated_at = models.DateTimeField('آخرین تغییر', auto_now=True)
    ip_address = models.GenericIPAddressField('آی‌پی', null=True, blank=True)

    class Meta:
        ordering = ['date', 'time']
        verbose_name = 'رزرو'
        verbose_name_plural = 'رزروها'
        indexes = [models.Index(fields=['date', 'time'], name='reservation_slot_idx')]

    def __str__(self):
        return f'{self.code} — {self.name}'

    def save(self, *args, **kwargs):
        if self.code:
            return super().save(*args, **kwargs)
        # Pick an unused code; retry if a concurrent booking grabbed the same
        # one between the check and the insert.
        for attempt in range(CODE_ATTEMPTS):
            self.code = self._unique_code()
            try:
                with transaction.atomic():
                    return super().save(*args, **kwargs)
            except IntegrityError:
                if attempt == CODE_ATTEMPTS - 1:
                    raise
                self.code = ''

    @classmethod
    def _unique_code(cls):
        while True:
            code = generate_code()
            if not cls.objects.filter(code=code).exists():
                return code

    @property
    def is_active(self):
        return self.status in {self.Status.PENDING, self.Status.CONFIRMED}
