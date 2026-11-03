from pathlib import Path
import logging

from django.conf import settings as django_settings
from django.contrib import messages
from django.contrib.auth import logout
from django.contrib.auth.decorators import login_required
from django.http import FileResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils.text import slugify

from .models import Document

MODEL_LABELS = [
    'Aadhaar Card', 'Certificates', 'Driving License', 'Government Documents',
    'Marksheet', 'Medical Reports', 'Other Documents', 'PAN Card', 'Passport',
    'Property Papers',
]
MODEL = None
logger = logging.getLogger(__name__)


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
        return MODEL_LABELS[int(np.argmax(prediction[0]))]
    except Exception as exc:
        logger.exception('Document classification failed: %s', exc)
        return 'Other Documents'


def _document_context(document):
    return {
        'id': document.id, 'name': document.name, 'category': document.category,
        'uploaded_on': document.uploaded_at.strftime('%Y-%m-%d'),
        'file_type': Path(document.file.name).suffix.lstrip('.').upper() or 'FILE',
        'status': 'Active', 'file_url': document.file.url,
        'download_url': reverse('download_document', args=[document.id]),
    }


@login_required
def dashboard(request):
    user_documents = Document.objects.filter(owner=request.user)
    documents = [_document_context(doc) for doc in user_documents[:5]]
    categories = [
        {'name': category, 'slug': slugify(category), 'count': user_documents.filter(category=category).count(), 'icon': 'fas fa-folder-open'}
        for category in MODEL_LABELS if user_documents.filter(category=category).exists()
    ]
    return render(request, 'documents/dashboard.html', {
        'title': 'Dashboard', 'welcome_name': request.user.first_name or request.user.username,
        'stats': [
            {'label': 'Total Documents', 'value': user_documents.count(), 'icon': 'fas fa-file-alt'},
            {'label': 'This Month', 'value': user_documents.count(), 'icon': 'fas fa-cloud-upload-alt'},
            {'label': 'Categories', 'value': len(categories), 'icon': 'fas fa-layer-group'},
            {'label': 'Storage Used', 'value': '—', 'icon': 'fas fa-database'},
        ], 'recent_documents': documents, 'categories': categories,
    })


@login_required
def documents_list(request):
    user_documents = Document.objects.filter(owner=request.user)
    query = request.GET.get('q', '').strip()
    category = request.GET.get('category', '').strip()
    sort = request.GET.get('sort', 'newest')
    if query:
        user_documents = user_documents.filter(name__icontains=query) | user_documents.filter(category__icontains=query)
    if category:
        user_documents = user_documents.filter(category=category)
    if sort == 'oldest':
        user_documents = user_documents.order_by('uploaded_at')
    elif sort == 'name':
        user_documents = user_documents.order_by('name')
    return render(request, 'documents/documents.html', {
        'title': 'My Documents',
        'documents': [_document_context(doc) for doc in user_documents],
        'categories': MODEL_LABELS, 'selected_category': category,
        'query': query, 'selected_sort': sort,
    })


@login_required
def upload_document(request):
    if request.method == 'POST':
        uploaded_file = request.FILES.get('file')
        if not uploaded_file:
            messages.error(request, 'Please select a file to upload.')
        elif uploaded_file.size > 10 * 1024 * 1024:
            messages.error(request, 'File size must be 10 MB or less.')
        else:
            name = request.POST.get('document_name', '').strip() or Path(uploaded_file.name).stem
            category = request.POST.get('category', '').strip()
            if not category or category == 'Auto-detect with ML':
                category = classify_document(uploaded_file)
            uploaded_file.seek(0)
            document = Document.objects.create(
                owner=request.user, name=name, file=uploaded_file,
                category=category, description=request.POST.get('description', '').strip(),
            )
            messages.success(request, f'{document.name} uploaded and categorized as {document.category}.')
            return redirect('documents')
    return render(request, 'documents/upload.html', {'title': 'Upload Document', 'categories': MODEL_LABELS})


@login_required
def categories(request):
    user_documents = Document.objects.filter(owner=request.user)
    rows = []
    for label in MODEL_LABELS:
        category_documents = user_documents.filter(category=label)
        rows.append({
            'name': label, 'slug': slugify(label), 'count': category_documents.count(),
            'icon': 'fas fa-folder-open',
            'documents': [_document_context(doc) for doc in category_documents],
        })
    return render(request, 'documents/categories.html', {'title': 'Categories', 'categories': rows})


@login_required
def category_detail(request, category_slug):
    category = next((label for label in MODEL_LABELS if slugify(label) == category_slug), None)
    if category is None:
        return redirect('categories')
    documents = Document.objects.filter(owner=request.user, category=category)
    return render(request, 'documents/category_detail.html', {
        'title': category, 'category': category,
        'documents': [_document_context(doc) for doc in documents],
    })


@login_required
def search_documents(request):
    query = request.GET.get('q', '').strip()
    documents = Document.objects.filter(owner=request.user)
    if query:
        documents = documents.filter(name__icontains=query) | documents.filter(category__icontains=query)
    return render(request, 'documents/search.html', {
        'title': 'Search Documents',
        'documents': [_document_context(doc) for doc in documents],
        'filter_options': ['All Documents', *MODEL_LABELS], 'query': query,
    })


@login_required
def document_view(request, doc_id):
    document = get_object_or_404(Document, id=doc_id, owner=request.user)
    return render(request, 'documents/document_view.html', {'title': 'Document Preview', 'document': _document_context(document)})


@login_required
def download_document(request, doc_id):
    document = get_object_or_404(Document, id=doc_id, owner=request.user)
    return FileResponse(document.file.open('rb'), as_attachment=True, filename=Path(document.file.name).name)


@login_required
def delete_document(request, doc_id):
    document = get_object_or_404(Document, id=doc_id, owner=request.user)
    if request.method == 'POST':
        try:
            if document.file and not document.file.closed:
                document.file.close()
            document.file.delete(save=False)
        except OSError:
            # A recently downloaded file can still be locked briefly on Windows.
            # The database record is still removed so it disappears immediately.
            pass
        document.delete()
        messages.success(request, 'Document deleted successfully.')
        return redirect('documents')
    return render(request, 'documents/delete_confirm.html', {'title': 'Delete Document', 'document': _document_context(document)})


@login_required
def profile(request):
    profile_data = {
        'name': request.user.get_full_name() or request.user.username,
        'email': request.user.email, 'role': 'Document Manager',
        'department': 'Administration Office',
    }
    return render(request, 'documents/profile.html', {'title': 'Profile', 'profile': profile_data})


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
                request.user.save(update_fields=['password'])
                messages.success(request, 'Password updated. Please log in again.')
                logout(request)
                return redirect('login')
            return redirect('settings')
        full_name = request.POST.get('full_name', '').strip()
        email = request.POST.get('email', '').strip().lower()
        if not full_name or not email:
            messages.error(request, 'Name and email are required.')
        elif request.user.__class__.objects.exclude(pk=request.user.pk).filter(email=email).exists():
            messages.error(request, 'That email is already used by another account.')
        else:
            first_name, *last_names = full_name.split()
            request.user.first_name = first_name
            request.user.last_name = ' '.join(last_names)
            request.user.email = email
            request.user.save(update_fields=['first_name', 'last_name', 'email'])
            messages.success(request, 'Account details updated successfully.')
            return redirect('settings')
    return render(request, 'documents/settings.html', {
        'title': 'Settings',
        'account': {'name': request.user.get_full_name(), 'email': request.user.email},
    })


def logout_view(request):
    logout(request)
    return redirect('login')
