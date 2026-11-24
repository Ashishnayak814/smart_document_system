from pathlib import Path
import logging
import re
from datetime import datetime, timezone

from django.conf import settings as django_settings
from django.contrib import messages
from django.contrib.auth import logout
from django.contrib.auth.decorators import login_required
from django.core.files.storage import default_storage
from django.http import FileResponse, Http404
from django.shortcuts import redirect, render
from django.urls import reverse
from django.utils.text import slugify

from smart_document_system.mongodb import ensure_indexes, get_collection
from smart_document_system.repositories import MongoRepository, as_object_id, utcnow

MODEL_LABELS = ['Aadhaar Card', 'Certificates', 'Driving License', 'Government Documents', 'Marksheet', 'Medical Reports', 'Other Documents', 'PAN Card', 'Passport', 'Property Papers']
MODEL = None
logger = logging.getLogger(__name__)
documents_repo = MongoRepository('documents')


def classify_document(file_path):
    """Classify an image with the bundled 224x224 Keras model."""
    global MODEL
    try:
        import numpy as np
        from PIL import Image
        from tensorflow.keras.models import load_model
        if MODEL is None:
            MODEL = load_model(django_settings.BASE_DIR / 'best_custom_model.keras', compile=False)
        image = Image.open(file_path).convert('RGB').resize((224, 224))
        prediction = MODEL.predict(np.expand_dims(np.asarray(image, dtype='float32') / 255.0, 0), verbose=0)
        scores = prediction[0]
        index = int(np.argmax(scores))
        return MODEL_LABELS[index], float(scores[index])
    except Exception as exc:
        logger.exception('Document classification failed: %s', exc)
        return 'Other Documents', 0.0


def _mongo_setup():
    ensure_indexes()


def _owned_document(doc_id, user_id):
    try:
        document = documents_repo.get(doc_id, extra_filter={'owner_id': as_object_id(user_id)})
    except ValueError:
        document = None
    if not document:
        raise Http404('Document not found')
    return document


def _document_context(document):
    storage_path = document.get('storage_path', '')
    return {'id': str(document['_id']), 'name': document['name'], 'category': document['category'], 'uploaded_on': document['uploaded_at'].strftime('%Y-%m-%d'), 'file_type': document.get('file_type') or Path(document.get('original_filename', '')).suffix.lstrip('.').upper() or 'FILE', 'status': document.get('processing_status', 'Active'), 'file_url': default_storage.url(storage_path) if storage_path else '', 'download_url': reverse('download_document', args=[document['_id']])}


def _user_filter(request):
    return {'owner_id': as_object_id(request.user.pk)}


@login_required
def dashboard(request):
    _mongo_setup()
    user_documents = documents_repo.many(_user_filter(request), sort=[('uploaded_at', -1)])
    categories = [{'name': category, 'slug': slugify(category), 'count': sum(doc.get('category') == category for doc in user_documents), 'icon': 'fas fa-folder-open'} for category in MODEL_LABELS if any(doc.get('category') == category for doc in user_documents)]
    return render(request, 'documents/dashboard.html', {'title': 'Dashboard', 'welcome_name': request.user.first_name or request.user.username, 'stats': [{'label': 'Total Documents', 'value': len(user_documents), 'icon': 'fas fa-file-alt'}, {'label': 'This Month', 'value': len(user_documents), 'icon': 'fas fa-cloud-upload-alt'}, {'label': 'Categories', 'value': len(categories), 'icon': 'fas fa-layer-group'}, {'label': 'Storage Used', 'value': '—', 'icon': 'fas fa-database'}], 'recent_documents': [_document_context(doc) for doc in user_documents[:5]], 'categories': categories})


@login_required
def documents_list(request):
    _mongo_setup()
    filters = _user_filter(request)
    query = request.GET.get('q', '').strip()
    category = request.GET.get('category', '').strip()
    sort = request.GET.get('sort', 'newest')
    if query:
        safe_query = re.escape(query)
        filters['$or'] = [{'name': {'$regex': safe_query, '$options': 'i'}}, {'category': {'$regex': safe_query, '$options': 'i'}}]
    if category:
        filters['category'] = category
    ordering = [('name', 1)] if sort == 'name' else [('uploaded_at', 1 if sort == 'oldest' else -1)]
    return render(request, 'documents/documents.html', {'title': 'My Documents', 'documents': [_document_context(doc) for doc in documents_repo.many(filters, sort=ordering)], 'categories': MODEL_LABELS, 'selected_category': category, 'query': query, 'selected_sort': sort})


@login_required
def upload_document(request):
    if request.method == 'POST':
        _mongo_setup()
        uploaded_file = request.FILES.get('file')
        if not uploaded_file:
            messages.error(request, 'Please select a file to upload.')
        elif uploaded_file.size > 10 * 1024 * 1024:
            messages.error(request, 'File size must be 10 MB or less.')
        else:
            name = request.POST.get('document_name', '').strip() or Path(uploaded_file.name).stem
            category = request.POST.get('category', '').strip()
            confidence = None
            if not category or category == 'Auto-detect with ML':
                category, confidence = classify_document(uploaded_file)
            uploaded_file.seek(0)
            storage_path = default_storage.save(f"documents/{datetime.now(timezone.utc):%Y/%m/%d}/{uploaded_file.name}", uploaded_file)
            document = documents_repo.insert({'owner_id': as_object_id(request.user.pk), 'name': name, 'original_filename': uploaded_file.name, 'file_type': Path(uploaded_file.name).suffix.lstrip('.').upper(), 'file_size': uploaded_file.size, 'storage_path': storage_path, 'category': category, 'description': request.POST.get('description', '').strip(), 'uploaded_at': utcnow(), 'processing_status': 'completed'})
            result = get_collection('classification_results').insert_one({'document_id': document['_id'], 'user_id': as_object_id(request.user.pk), 'predicted_category': category, 'confidence_score': confidence, 'processed_at': utcnow()})
            documents_repo.update(document['_id'], {'classification_result_id': result.inserted_id})
            get_collection('activity_logs').insert_one({'user_id': as_object_id(request.user.pk), 'action': 'document_uploaded', 'document_id': document['_id'], 'created_at': utcnow()})
            messages.success(request, f'{name} uploaded and categorized as {category}.')
            return redirect('documents')
    return render(request, 'documents/upload.html', {'title': 'Upload Document', 'categories': MODEL_LABELS})


@login_required
def categories(request):
    _mongo_setup()
    user_documents = documents_repo.many(_user_filter(request), sort=[('uploaded_at', -1)])
    rows = []
    for label in MODEL_LABELS:
        category_documents = [doc for doc in user_documents if doc.get('category') == label]
        rows.append({'name': label, 'slug': slugify(label), 'count': len(category_documents), 'icon': 'fas fa-folder-open', 'documents': [_document_context(doc) for doc in category_documents]})
    return render(request, 'documents/categories.html', {'title': 'Categories', 'categories': rows})


@login_required
def category_detail(request, category_slug):
    _mongo_setup()
    category = next((label for label in MODEL_LABELS if slugify(label) == category_slug), None)
    if category is None:
        return redirect('categories')
    documents = documents_repo.many({**_user_filter(request), 'category': category}, sort=[('uploaded_at', -1)])
    return render(request, 'documents/category_detail.html', {'title': category, 'category': category, 'documents': [_document_context(doc) for doc in documents]})


@login_required
def search_documents(request):
    _mongo_setup()
    query = request.GET.get('q', '').strip()
    filters = _user_filter(request)
    if query:
        safe_query = re.escape(query)
        filters['$or'] = [{'name': {'$regex': safe_query, '$options': 'i'}}, {'category': {'$regex': safe_query, '$options': 'i'}}]
    documents = documents_repo.many(filters, sort=[('uploaded_at', -1)])
    return render(request, 'documents/search.html', {'title': 'Search Documents', 'documents': [_document_context(doc) for doc in documents], 'filter_options': ['All Documents', *MODEL_LABELS], 'query': query})


@login_required
def document_view(request, doc_id):
    _mongo_setup()
    return render(request, 'documents/document_view.html', {'title': 'Document Preview', 'document': _document_context(_owned_document(doc_id, request.user.pk))})


@login_required
def download_document(request, doc_id):
    _mongo_setup()
    document = _owned_document(doc_id, request.user.pk)
    try:
        return FileResponse(default_storage.open(document['storage_path'], 'rb'), as_attachment=True, filename=document['original_filename'])
    except (FileNotFoundError, OSError):
        raise Http404('Document file is unavailable')


@login_required
def delete_document(request, doc_id):
    _mongo_setup()
    document = _owned_document(doc_id, request.user.pk)
    if request.method == 'POST':
        default_storage.delete(document['storage_path'])
        documents_repo.delete(document['_id'], extra_filter=_user_filter(request))
        get_collection('classification_results').delete_one({'document_id': document['_id'], 'user_id': as_object_id(request.user.pk)})
        get_collection('activity_logs').insert_one({'user_id': as_object_id(request.user.pk), 'action': 'document_deleted', 'document_id': document['_id'], 'created_at': utcnow()})
        messages.success(request, 'Document deleted successfully.')
        return redirect('documents')
    return render(request, 'documents/delete_confirm.html', {'title': 'Delete Document', 'document': _document_context(document)})


@login_required
def profile(request):
    return render(request, 'documents/profile.html', {'title': 'Profile', 'profile': {'name': request.user.get_full_name() or request.user.username, 'email': request.user.email, 'role': 'Document Manager', 'department': 'Administration Office'}})


@login_required
def settings(request):
    if request.method == 'POST':
        if request.POST.get('new_password'):
            if not request.user.check_password(request.POST.get('current_password', '')):
                messages.error(request, 'Current password is incorrect.')
            elif request.POST.get('new_password') != request.POST.get('confirm_password'):
                messages.error(request, 'New passwords do not match.')
            else:
                request.user.set_password(request.POST['new_password'])
                request.user.save()
                messages.success(request, 'Password updated. Please log in again.')
                logout(request)
                return redirect('login')
            return redirect('settings')
        full_name = request.POST.get('full_name', '').strip()
        email = request.POST.get('email', '').strip().lower()
        if not full_name or not email:
            messages.error(request, 'Name and email are required.')
        elif get_collection('users').find_one({'email': email, '_id': {'$ne': as_object_id(request.user.pk)}}):
            messages.error(request, 'That email is already used by another account.')
        else:
            first_name, *last_names = full_name.split()
            request.user.email, request.user.username = email, email
            request.user.first_name, request.user.last_name = first_name, ' '.join(last_names)
            request.user.save()
            messages.success(request, 'Account details updated successfully.')
            return redirect('settings')
    return render(request, 'documents/settings.html', {'title': 'Settings', 'account': {'name': request.user.get_full_name(), 'email': request.user.email}})


def logout_view(request):
    logout(request)
    return redirect('login')
