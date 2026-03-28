from functools import wraps
from django.shortcuts import redirect
from django.contrib import messages


def seller_required(view_func):
    @wraps(view_func)
    def wrapper(request, *args, **kwargs):
        if request.user.is_seller and hasattr(request.user, 'seller_profile') and request.user.seller_profile.approved:
            return view_func(request, *args, **kwargs)
        messages.error(request, "Access denied. Sellers only.")
        return redirect('home')
    return wrapper


def customer_required(view_func):
    @wraps(view_func)
    def wrapper(request, *args, **kwargs):
        if request.user.is_customer:
            return view_func(request, *args, **kwargs)
        messages.error(request, "Access denied. Customers only.")
        return redirect('home')
    return wrapper


def admin_required(view_func):
    @wraps(view_func)
    def wrapper(request, *args, **kwargs):
        if request.user.is_staff or request.user.is_superuser:
            return view_func(request, *args, **kwargs)
        messages.error(request, "Access denied. Admins only.")
        return redirect('home')
    return wrapper
