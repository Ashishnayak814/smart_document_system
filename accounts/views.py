import hashlib
import logging
import re
import secrets
from datetime import datetime, timedelta, timezone

from django.conf import settings
from django.contrib import messages
from django.contrib.auth import authenticate, login
from django.core.mail import send_mail
from django.shortcuts import redirect, render
from django.urls import reverse

from smart_document_system.mongodb import ensure_indexes, get_collection
from django.contrib.auth.hashers import make_password
from .mongo_auth import MongoUser

logger = logging.getLogger(__name__)


def login_page(request):
    if request.user.is_authenticated:
        return redirect('dashboard')
    if request.method == 'POST':
        ensure_indexes()
        email = request.POST.get('email', '').strip().lower()
        user = authenticate(request, username=email, password=request.POST.get('password', ''))
        if isinstance(user, MongoUser):
            login(request, user)
            return redirect(request.GET.get('next') or 'dashboard')
        if user is not None:
            messages.error(request, 'This legacy account must be migrated before using SmartDocs.')
        else:
            messages.error(request, 'Invalid email or password.')
    return render(request, 'accounts/login.html', {'auth_layout': True})


def register_page(request):
    if request.user.is_authenticated:
        return redirect('dashboard')
    if request.method == 'POST':
        ensure_indexes()
        full_name = request.POST.get('full_name', '').strip()
        email = request.POST.get('email', '').strip().lower()
        password = request.POST.get('password', '')
        if not full_name or not email or not password:
            messages.error(request, 'Please fill in all required fields.')
        elif password != request.POST.get('confirm_password', ''):
            messages.error(request, 'Passwords do not match.')
        elif get_collection('users').find_one({'email': email}):
            messages.error(request, 'An account with this email already exists.')
        else:
            first_name, *last_names = full_name.split()
            now_user = {'email': email, 'password': make_password(password), 'first_name': first_name, 'last_name': ' '.join(last_names), 'is_active': True}
            result = get_collection('users').insert_one(now_user)
            user = MongoUser(get_collection('users').find_one({'_id': result.inserted_id}))
            login(request, user)
            return redirect('dashboard')
    return render(request, 'accounts/register.html', {'auth_layout': True})


def forgot_password(request):
    reset_link = None
    if request.method == 'POST':
        email = request.POST.get('email', '').strip().lower()
        user = get_collection('users').find_one({
            'email': {'$regex': f'^{re.escape(email)}$', '$options': 'i'},
            'is_active': True,
        }) if email else None

        # Always show the same response so the page cannot be used to discover
        # which email addresses have accounts.
        messages.success(request, 'If an account exists for that email, a reset link has been sent.')
        if user:
            email = user['email']
            raw_token = secrets.token_urlsafe(32)
            token_hash = hashlib.sha256(raw_token.encode('utf-8')).hexdigest()
            get_collection('password_reset_tokens').delete_many({'email': email})
            get_collection('password_reset_tokens').insert_one({
                'email': email,
                'token_hash': token_hash,
                'expires_at': datetime.now(timezone.utc) + timedelta(minutes=30),
                'created_at': datetime.now(timezone.utc),
            })
            reset_link = f"{settings.APP_BASE_URL}{reverse('reset_password', args=[raw_token])}"
            try:
                send_mail(
                    'SmartDocs password reset',
                    f'Use this link to reset your password: {reset_link}',
                    getattr(settings, 'DEFAULT_FROM_EMAIL', 'noreply@smartdocs.local'),
                    [email],
                    fail_silently=False,
                )
            except Exception:
                logger.exception('Password reset email could not be sent')
                messages.error(request, 'We could not send the reset email. Please try again later.')
    return render(request, 'accounts/forgot_password.html', {'auth_layout': True, 'reset_link': reset_link})


def reset_password(request, token):
    token_hash = hashlib.sha256(token.encode('utf-8')).hexdigest()
    reset_token = get_collection('password_reset_tokens').find_one({'token_hash': token_hash})
    now = datetime.now(timezone.utc)
    expires_at = reset_token.get('expires_at') if reset_token else None
    if expires_at and expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=timezone.utc)
    if not reset_token or not expires_at or expires_at <= now:
        messages.error(request, 'This password reset link is invalid or expired.')
        return redirect('forgot_password')

    if request.method == 'POST':
        password = request.POST.get('password', '')
        confirm_password = request.POST.get('confirm_password', '')
        if len(password) < 8:
            messages.error(request, 'Password must be at least 8 characters long.')
        elif password != confirm_password:
            messages.error(request, 'Passwords do not match.')
        else:
            user = get_collection('users').find_one({'email': reset_token['email'], 'is_active': True})
            if not user:
                messages.error(request, 'This password reset link is invalid or expired.')
                return redirect('forgot_password')
            get_collection('users').update_one({'_id': user['_id']}, {'$set': {'password': make_password(password), 'updated_at': now}})
            get_collection('password_reset_tokens').delete_one({'_id': reset_token['_id']})
            messages.success(request, 'Your password has been updated. Please log in.')
            return redirect('login')

    return render(request, 'accounts/reset_password.html', {'auth_layout': True})
