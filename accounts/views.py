from django.contrib import messages
from django.contrib.auth import authenticate, login
from django.contrib.auth.models import User
from django.shortcuts import redirect, render


def login_page(request):
    if request.user.is_authenticated:
        return redirect('dashboard')
    if request.method == 'POST':
        email = request.POST.get('email', '').strip().lower()
        user = authenticate(request, username=email, password=request.POST.get('password', ''))
        if user is not None:
            login(request, user)
            return redirect(request.GET.get('next') or 'dashboard')
        messages.error(request, 'Invalid email or password.')
    return render(request, 'accounts/login.html', {'auth_layout': True})


def register_page(request):
    if request.user.is_authenticated:
        return redirect('dashboard')
    if request.method == 'POST':
        full_name = request.POST.get('full_name', '').strip()
        email = request.POST.get('email', '').strip().lower()
        password = request.POST.get('password', '')
        if not full_name or not email or not password:
            messages.error(request, 'Please fill in all required fields.')
        elif password != request.POST.get('confirm_password', ''):
            messages.error(request, 'Passwords do not match.')
        elif User.objects.filter(username=email).exists() or User.objects.filter(email=email).exists():
            messages.error(request, 'An account with this email already exists.')
        else:
            first_name, *last_names = full_name.split()
            user = User.objects.create_user(username=email, email=email, password=password, first_name=first_name, last_name=' '.join(last_names))
            login(request, user)
            return redirect('dashboard')
    return render(request, 'accounts/register.html', {'auth_layout': True})
