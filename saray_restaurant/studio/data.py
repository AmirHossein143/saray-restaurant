"""Describe the project's database tables and (de)serialize their rows for the Data Studio.

Nothing here talks to the request: it is plain introspection of Django models so
the browser UI can be fully generic. Rows are always validated through
``ModelForm`` (see ``views.py``), never written with raw SQL.
"""

import datetime
import decimal
import json

from django.apps import apps
from django.db import models
from django.db.models import Q
from django.utils import timezone

# Tables that are shown but cannot be changed from the studio.
READONLY = {
    'auth.user': 'Manage users from the Django admin so password hashes stay protected.',
    'auth.group': 'Edit groups from the Django admin.',
    'auth.permission': 'System table, view only.',
    'contenttypes.contenttype': 'System table, view only.',
    'admin.logentry': 'Django admin change history, view only.',
}
# Tables that are not shown at all (they hold login sessions).
HIDDEN_MODELS = {'sessions.session'}
# Columns that never leave the server.
HIDDEN_FIELDS = {'auth.user': {'password'}}
# One-row tables: cannot add a second row or delete the only one.
SINGLETONS = {'saray_menu.sitesettings'}

GROUP_ORDER = ['saray_menu', 'reservations', 'auth', 'admin', 'contenttypes']
GROUP_LABELS = {
    'saray_menu': 'Menu & site',
    'reservations': 'Reservations',
    'auth': 'Users & access',
    'admin': 'System',
    'contenttypes': 'System',
}
TEXT_LIMIT = 240  # characters of a text cell sent in list responses


def model_key(model):
    return f'{model._meta.app_label}.{model._meta.model_name}'


def visible_models():
    result = [m for m in apps.get_models() if model_key(m) not in HIDDEN_MODELS]
    result.sort(key=lambda m: (
        GROUP_ORDER.index(m._meta.app_label) if m._meta.app_label in GROUP_ORDER else 99,
        m._meta.object_name.lower(),
    ))
    return result


def get_model(key):
    """Return the model for ``'app_label.model_name'`` or ``None`` if unknown or hidden."""
    if key in HIDDEN_MODELS:
        return None
    try:
        app_label, model_name = key.split('.', 1)
        return apps.get_model(app_label, model_name)
    except (ValueError, LookupError):
        return None


def is_readonly(model):
    return model_key(model) in READONLY


def hidden_fields(model):
    return HIDDEN_FIELDS.get(model_key(model), set())


def columns(model):
    """Concrete columns shown in the table (primary key first)."""
    hidden = hidden_fields(model)
    fields = [f for f in model._meta.concrete_fields if f.name not in hidden]
    fields.sort(key=lambda f: not f.primary_key)
    return fields


def form_fields(model):
    """Names of the fields the add/edit form offers."""
    hidden = hidden_fields(model)
    return [
        f.name for f in model._meta.concrete_fields
        if f.editable and not f.primary_key and f.name not in hidden
    ]


def field_kind(f):
    if f.choices:
        return 'choice'
    if isinstance(f, (models.ForeignKey, models.OneToOneField)):
        return 'fk'
    if isinstance(f, models.BooleanField):
        return 'bool'
    if isinstance(f, models.ImageField):
        return 'image'
    if isinstance(f, models.FileField):
        return 'file'
    if isinstance(f, models.DateTimeField):  # before DateField: it is a subclass
        return 'datetime'
    if isinstance(f, models.DateField):
        return 'date'
    if isinstance(f, models.TimeField):
        return 'time'
    if isinstance(f, models.EmailField):
        return 'email'
    if isinstance(f, models.URLField):
        return 'url'
    if isinstance(f, models.IntegerField):  # includes AutoField / BigAutoField
        return 'number'
    if isinstance(f, (models.DecimalField, models.FloatField)):
        return 'decimal'
    if isinstance(f, models.JSONField):
        return 'json'
    if isinstance(f, models.TextField):
        return 'textarea'
    return 'text'


def describe_field(f):
    kind = field_kind(f)
    info = {
        'name': f.name,
        'label': f.name,
        'verbose': str(f.verbose_name),
        'kind': kind,
        'pk': f.primary_key,
        'editable': bool(f.editable and not f.primary_key),
        'required': not f.blank and kind != 'bool',
        'null': f.null,
        'unique': f.unique and not f.primary_key,
        'help': str(f.help_text or ''),
        'max_length': f.max_length,
    }
    if f.has_default():
        default = f.get_default()
        if isinstance(default, (bool, int, float, str)):
            info['default'] = default
    if kind == 'choice':
        info['choices'] = [[str(v), str(label)] for v, label in f.flatchoices]
    if kind == 'fk':
        info['related'] = model_key(f.remote_field.model)
    if kind == 'number':
        for validator in f.validators:
            name = validator.__class__.__name__
            if name == 'MinValueValidator':
                info['min'] = validator.limit_value
            elif name == 'MaxValueValidator':
                info['max'] = validator.limit_value
    return info


def describe_model(model, count=None):
    key = model_key(model)
    meta = model._meta
    readonly = is_readonly(model)
    can_add = not readonly
    can_delete = not readonly
    if key in SINGLETONS:
        can_delete = False
        can_add = can_add and not model.objects.exists()
    app_label = meta.app_label
    return {
        'key': key,
        'name': meta.object_name,
        'table': meta.db_table,
        'verbose': str(meta.verbose_name_plural),
        'group': GROUP_LABELS.get(app_label, app_label),
        'count': model.objects.count() if count is None else count,
        'readonly': readonly,
        'note': READONLY.get(key, ''),
        'singleton': key in SINGLETONS,
        'can_add': can_add,
        'can_delete': can_delete,
        'fields': [describe_field(f) for f in columns(model)],
        'form_fields': form_fields(model),
        'ordering': list(meta.ordering) or ['-pk'],
        'has_slug': any(f.name == 'slug' for f in meta.concrete_fields),
    }


# --------------------------------------------------------------------------
# Row (de)serialization
# --------------------------------------------------------------------------


def _isoformat(value):
    if isinstance(value, datetime.datetime):
        if timezone.is_aware(value):
            value = timezone.localtime(value)
        return value.isoformat(timespec='seconds')
    return value.isoformat()


def _file_url(value):
    if not value:
        return None
    try:
        return value.url
    except ValueError:
        return None


def display_value(f, obj, limit=TEXT_LIMIT):
    """JSON-safe value of column ``f`` for the table."""
    kind = field_kind(f)
    raw = f.value_from_object(obj)
    if raw is None:
        return None
    if kind == 'fk':
        related = getattr(obj, f.name, None)
        return {'id': raw, 'label': str(related) if related is not None else str(raw)}
    if kind == 'choice':
        return {'value': raw, 'label': str(dict(f.flatchoices).get(raw, raw))}
    if kind in ('image', 'file'):
        return _file_url(raw)
    if kind in ('datetime', 'date', 'time'):
        return _isoformat(raw)
    if kind == 'json':
        raw = json.dumps(raw, ensure_ascii=False)
    if isinstance(raw, decimal.Decimal):
        return str(raw)
    if isinstance(raw, str):
        return raw if limit is None or len(raw) <= limit else raw[:limit] + '…'
    if isinstance(raw, (bool, int, float)):
        return raw
    return str(raw)


def serialize_row(model, obj, cols=None):
    return {
        'pk': obj.pk,
        'label': str(obj),
        'v': {f.name: display_value(f, obj) for f in (cols or columns(model))},
    }


def form_value(f, obj):
    """Value for an ``<input>`` in the edit form."""
    kind = field_kind(f)
    raw = f.value_from_object(obj)
    if raw is None:
        return None
    if kind == 'datetime':
        if timezone.is_aware(raw):
            raw = timezone.localtime(raw)
        return raw.strftime('%Y-%m-%dT%H:%M')
    if kind == 'date':
        return raw.isoformat()
    if kind == 'time':
        return raw.strftime('%H:%M')
    if kind in ('image', 'file'):
        return _file_url(raw)
    if kind == 'json':
        return json.dumps(raw, ensure_ascii=False, indent=2)
    if isinstance(raw, (bool, int, float)):
        return raw
    return str(raw)


def serialize_detail(model, obj):
    names = set(form_fields(model))
    return {
        'pk': obj.pk,
        'label': str(obj),
        'form': {f.name: form_value(f, obj) for f in columns(model) if f.name in names},
    }


# --------------------------------------------------------------------------
# Querying
# --------------------------------------------------------------------------

TEXT_KINDS = {'text', 'textarea', 'email', 'url'}


def build_queryset(model, params):
    """Apply search, filters and sorting from query ``params`` (a ``QueryDict``)."""
    cols = {f.name: f for f in columns(model)}
    qs = model._default_manager.all()
    fk_names = [n for n, f in cols.items() if field_kind(f) == 'fk']
    if fk_names:
        qs = qs.select_related(*fk_names)

    term = (params.get('q') or '').strip()
    if term:
        query = Q()
        for f in cols.values():
            if field_kind(f) in TEXT_KINDS:
                query |= Q(**{f'{f.name}__icontains': term})
        if term.isdigit():
            query |= Q(pk=int(term))
        qs = qs.filter(query)

    for name, f in cols.items():
        value = params.get(f'f_{name}')
        if value in (None, ''):
            continue
        kind = field_kind(f)
        if kind == 'bool':
            qs = qs.filter(**{name: value in ('1', 'true', 'True')})
        elif kind in ('choice', 'fk'):
            qs = qs.filter(**{name: value})
        elif kind in ('image', 'file'):
            qs = qs.exclude(**{name: ''}) if value == 'yes' else qs.filter(**{name: ''})

    sort = params.get('sort') or ''
    name = sort.lstrip('-')
    if name in cols:
        qs = qs.order_by(sort, '-pk' if sort.startswith('-') else 'pk')
    elif not model._meta.ordering:
        qs = qs.order_by('-pk')
    return qs
