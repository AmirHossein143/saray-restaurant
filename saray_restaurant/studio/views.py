"""Data Studio: a superuser-only, JSON-backed table browser/editor.

Every write goes through a ``ModelForm`` so field validators, uniqueness checks
and ``Model.clean`` run exactly as they do in the Django admin. Each change is
recorded in the admin history (``LogEntry``). The UI is English on purpose: it is
for the site owner/developer, not for visitors.
"""

import csv
import json
import logging
from collections import Counter
from functools import wraps

from django.contrib.admin.models import ADDITION, CHANGE, DELETION, LogEntry
from django.contrib.auth.views import redirect_to_login
from django.core.paginator import Paginator
from django.db import router, transaction
from django.db.models.deletion import Collector, ProtectedError, RestrictedError
from django.forms import modelform_factory
from django.http import Http404, HttpResponse, JsonResponse
from django.shortcuts import render
from django.urls import reverse
from django.utils import translation
from django.views.decorators.csrf import ensure_csrf_cookie
from django.views.decorators.http import require_http_methods

from . import data

logger = logging.getLogger(__name__)

PAGE_SIZES = (10, 25, 50, 100, 250)
OPTIONS_LIMIT = 500
BULK_LIMIT = 500
CSV_DANGEROUS = ('=', '+', '-', '@', '\t', '\r')


# --------------------------------------------------------------------------
# Helpers
# --------------------------------------------------------------------------


def error(message, status=400, **extra):
    return JsonResponse({'error': message, **extra}, status=status)


def superuser_only(api=True):
    """Only active superusers may use the studio (it can edit any table)."""

    def decorator(view):
        @wraps(view)
        def wrapper(request, *args, **kwargs):
            user = request.user
            if not user.is_authenticated:
                if api:
                    return error('Sign in required.', 401)
                return redirect_to_login(request.get_full_path(), reverse('admin:login'))
            if not (user.is_active and user.is_superuser):
                if api:
                    return error('Superuser access required.', 403)
                return HttpResponse('Superuser access required.', status=403)
            if api:
                with translation.override('en'):
                    return view(request, *args, **kwargs)
            return view(request, *args, **kwargs)

        return wrapper

    return decorator


def resolve(key):
    model = data.get_model(key)
    if model is None:
        raise Http404(f'Unknown table: {key}')
    return model


def get_row(model, pk):
    try:
        return model._default_manager.get(pk=pk)
    except model.DoesNotExist:
        raise Http404('Row not found') from None


def writable(model):
    """An error response when the table is read-only, else ``None``."""
    if data.is_readonly(model):
        return error(data.READONLY[data.model_key(model)] or 'This table is read-only.', 403)
    return None


def log_change(request, objs, flag, message):
    try:
        LogEntry.objects.log_actions(
            request.user.pk, objs, flag, change_message=message, single_object=len(objs) == 1,
        )
    except Exception:  # noqa: BLE001 - history is best effort, never block the edit
        logger.exception('Could not write the admin history entry')


def form_errors(form):
    errors = {}
    for name, items in form.errors.get_json_data().items():
        errors[name] = [item['message'] for item in items]
    return errors


def parse_json(request):
    try:
        body = json.loads(request.body or b'{}')
    except ValueError:
        return None
    return body if isinstance(body, dict) else None


def auto_slug(model, post):
    """Fill an empty ``slug`` the way the Django admin does (from the English, then local name)."""
    if 'slug' not in data.form_fields(model) or (post.get('slug') or '').strip():
        return
    try:
        from saray_menu.admin import slug_source, unique_slug
    except ImportError:  # pragma: no cover - the menu app is part of this project
        return
    base = slug_source(post.get('name_en'), post.get('name'))
    post['slug'] = unique_slug(model, base)


def cascade_summary(model, objs):
    """What deleting ``objs`` would remove, or the reason it is blocked."""
    collector = Collector(using=router.db_for_write(model))
    try:
        collector.collect(list(objs))
    except (ProtectedError, RestrictedError) as exc:
        blockers = getattr(exc, 'protected_objects', None) or getattr(exc, 'restricted_objects', [])
        names = sorted({o._meta.object_name for o in blockers})
        return None, f'Blocked by related {", ".join(names) or "records"} that must be removed first.'
    counts = Counter()
    for related_model, instances in collector.data.items():
        counts[related_model] += len(instances)
    for queryset in collector.fast_deletes:
        counts[queryset.model] += queryset.count()
    counts[model] -= len(objs)
    related = [
        {'table': m._meta.object_name, 'count': n}
        for m, n in sorted(counts.items(), key=lambda item: item[0]._meta.object_name) if n > 0
    ]
    return {'selected': len(objs), 'related': related}, None


def delete_rows(request, model, objs):
    """Delete ``objs`` atomically. Returns an error response or ``None``."""
    labels = [str(o) for o in objs]
    try:
        with transaction.atomic():
            log_change(request, objs, DELETION, 'Deleted from Data Studio')
            for obj in objs:
                obj.delete()
    except (ProtectedError, RestrictedError):
        return error('Blocked: other records still depend on this row.', 409)
    logger.info('Data Studio: %s deleted %s %s', request.user, data.model_key(model), labels)
    return None


# --------------------------------------------------------------------------
# Pages and API
# --------------------------------------------------------------------------


@superuser_only(api=False)
@ensure_csrf_cookie
def index(request):
    return render(request, 'studio/index.html')


@superuser_only()
@require_http_methods(['GET'])
def tables(request):
    return JsonResponse({
        'tables': [data.describe_model(m) for m in data.visible_models()],
        'page_sizes': PAGE_SIZES,
    })


@superuser_only()
@require_http_methods(['GET', 'POST'])
def rows(request, key):
    model = resolve(key)
    if request.method == 'POST':
        return create_row(request, model)

    qs = data.build_queryset(model, request.GET)
    try:
        size = int(request.GET.get('page_size', 25))
    except ValueError:
        size = 25
    size = size if size in PAGE_SIZES else 25
    paginator = Paginator(qs, size)
    page = paginator.get_page(request.GET.get('page') or 1)
    cols = data.columns(model)
    return JsonResponse({
        'rows': [data.serialize_row(model, obj, cols) for obj in page],
        'page': page.number,
        'pages': paginator.num_pages,
        'total': paginator.count,
        'page_size': size,
        'start': page.start_index() if paginator.count else 0,
        'end': page.end_index() if paginator.count else 0,
    })


def create_row(request, model):
    blocked = writable(model)
    if blocked:
        return blocked
    key = data.model_key(model)
    if key in data.SINGLETONS and model.objects.exists():
        return error('This table holds exactly one row; edit the existing one.', 409)
    post = request.POST.copy()
    auto_slug(model, post)
    form_class = modelform_factory(model, fields=data.form_fields(model))
    form = form_class(post, request.FILES)
    if not form.is_valid():
        return JsonResponse({'error': 'Please fix the highlighted fields.', 'fields': form_errors(form)}, status=422)
    obj = form.save()
    log_change(request, [obj], ADDITION, 'Added from Data Studio')
    return JsonResponse({'row': data.serialize_row(model, obj), 'detail': data.serialize_detail(model, obj)}, status=201)


@superuser_only()
@require_http_methods(['GET', 'POST', 'PATCH', 'DELETE'])
def row(request, key, pk):
    model = resolve(key)
    obj = get_row(model, pk)
    if request.method == 'GET':
        return JsonResponse(data.serialize_detail(model, obj))
    blocked = writable(model)
    if blocked:
        return blocked

    if request.method == 'DELETE':
        if key in data.SINGLETONS:
            return error('This table holds exactly one row, so it cannot be deleted.', 403)
        failure = delete_rows(request, model, [obj])
        return failure or JsonResponse({'deleted': 1})

    names = data.form_fields(model)
    if request.method == 'POST':  # full edit from the side panel (multipart, may include files)
        form_class = modelform_factory(model, fields=names)
        form = form_class(request.POST, request.FILES, instance=obj)
    else:  # PATCH: inline edit of a single cell
        body = parse_json(request)
        if body is None or body.get('field') not in names:
            return error('Unknown or read-only field.')
        field = model._meta.get_field(body['field'])
        kind = data.field_kind(field)
        if kind in ('image', 'file'):
            return error('Files can only be changed from the edit panel.')
        value = body.get('value')
        values = {}
        if kind == 'bool':
            if value:
                values[field.name] = 'on'
        else:
            values[field.name] = '' if value is None else str(value)
        form_class = modelform_factory(model, fields=[field.name])
        form = form_class(values, instance=obj)
    if not form.is_valid():
        return JsonResponse({'error': 'Please fix the highlighted fields.', 'fields': form_errors(form)}, status=422)
    obj = form.save()
    log_change(request, [obj], CHANGE, 'Changed from Data Studio: ' + ', '.join(sorted(form.changed_data)))
    return JsonResponse({'row': data.serialize_row(model, obj), 'detail': data.serialize_detail(model, obj)})


@superuser_only()
@require_http_methods(['GET'])
def delete_preview(request, key, pk):
    model = resolve(key)
    obj = get_row(model, pk)
    summary, problem = cascade_summary(model, [obj])
    return JsonResponse({'label': str(obj), 'summary': summary, 'blocked': problem})


@superuser_only()
@require_http_methods(['POST'])
def bulk_delete(request, key):
    model = resolve(key)
    blocked = writable(model)
    if blocked:
        return blocked
    if key in data.SINGLETONS:
        return error('This table holds exactly one row, so it cannot be deleted.', 403)
    body = parse_json(request)
    ids = body.get('ids') if body else None
    if not isinstance(ids, list) or not ids or len(ids) > BULK_LIMIT or not all(isinstance(i, int) for i in ids):
        return error(f'Send between 1 and {BULK_LIMIT} row ids.')
    objs = list(model._default_manager.filter(pk__in=ids))
    if body.get('preview'):
        summary, problem = cascade_summary(model, objs)
        return JsonResponse({'summary': summary, 'blocked': problem})
    failure = delete_rows(request, model, objs)
    return failure or JsonResponse({'deleted': len(objs)})


@superuser_only()
@require_http_methods(['GET'])
def options(request, key):
    """Rows of a table as ``{id, label}`` pairs, for foreign-key dropdowns."""
    model = resolve(key)
    qs = model._default_manager.all()
    term = (request.GET.get('q') or '').strip().lower()
    items = []
    for obj in qs[: OPTIONS_LIMIT * 4]:
        label = str(obj)
        if not term or term in label.lower():
            items.append({'id': obj.pk, 'label': label})
        if len(items) >= OPTIONS_LIMIT:
            break
    return JsonResponse({'options': items})


def csv_cell(value):
    text = '' if value is None else str(value)
    if text.startswith(CSV_DANGEROUS):
        try:
            float(text)
        except ValueError:
            return "'" + text  # neutralise spreadsheet formula injection
    return text


@superuser_only()
@require_http_methods(['GET'])
def export_csv(request, key):
    model = resolve(key)
    cols = data.columns(model)
    qs = data.build_queryset(model, request.GET)
    response = HttpResponse(content_type='text/csv; charset=utf-8')
    response['Content-Disposition'] = f'attachment; filename="{model._meta.db_table}.csv"'
    response.write('﻿')  # lets Excel read Persian text correctly
    writer = csv.writer(response)
    writer.writerow([f.name for f in cols])
    for obj in qs.iterator():
        line = []
        for f in cols:
            value = data.display_value(f, obj, limit=None)
            if isinstance(value, dict):
                value = value.get('id', value.get('value'))
            line.append(csv_cell(value))
        writer.writerow(line)
    return response
