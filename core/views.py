from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.db.models import Q, Sum, Max
from django.db.models import Count, DecimalField, ExpressionWrapper, F, Avg
from django.db.models.functions import TruncMonth, TruncWeek
from django.utils import timezone
from django.http import Http404, HttpResponse, FileResponse
from django.core.files.base import ContentFile
from django.views.decorators.cache import never_cache
from django.views.decorators.csrf import ensure_csrf_cookie
import os
import zipfile
import csv
import calendar
import re
from decimal import Decimal
from reportlab.lib.pagesizes import A4
from reportlab.lib.utils import ImageReader
from reportlab.pdfgen import canvas

from .models import (
    User, SellerProfile, CustomerProfile,
    Product, ProductPreviewPage, DigitalBook, Chapter, ChapterPage,
    Order, OrderItem, CategoryChoice, RecentRead, Genre, ProductReview, CustomerFeedback
)
from .forms import (
    CustomerRegistrationForm, SellerRegistrationForm,
    ProductForm, DigitalBookForm, ChapterForm,
    MultiPageUploadForm, MultiProductPreviewUploadForm, CheckoutForm,
    BulkChapterUploadForm, ProductReviewForm, CustomerFeedbackForm
)
from .decorators import seller_required, customer_required, admin_required


# ═══════════════════════════════════════════════════════
# HELPERS
# ═══════════════════════════════════════════════════════
def get_cart(request):
    return request.session.get('cart', {})   # {product_id: quantity}


def save_cart(request, cart):
    request.session['cart'] = cart
    request.session.modified = True


def cart_item_count(request):
    return sum(get_cart(request).values())


def normalize_category_param(raw_value):
    """Map user-provided category values to canonical CategoryChoice keys."""
    if not raw_value:
        return ''

    value = str(raw_value).strip()
    if not value:
        return ''

    for key, label in CategoryChoice.choices:
        if value.upper() == key or value.lower() == str(label).lower():
            return key
    return ''


def save_product_preview_pages(product, image_files, reset_existing=False):
    """Persist uploaded preview images with sequential page numbers per product."""
    if reset_existing:
        product.preview_pages.all().delete()

    start_page = (
        product.preview_pages.aggregate(last=Max('page_number')).get('last') or 0
    ) + 1

    for offset, image in enumerate(image_files, start=0):
        ProductPreviewPage.objects.create(
            product=product,
            page_number=start_page + offset,
            image=image,
        )


def extract_cbz_to_pages(chapter):
    """Extract images from a CBZ file and persist them as ChapterPage rows."""
    if not chapter.chapter_file or chapter.file_extension() != 'cbz':
        return 0

    if chapter.pages.exists():
        return chapter.pages.count()

    allowed_exts = {'.jpg', '.jpeg', '.png', '.webp', '.gif'}
    extracted = 0

    chapter.chapter_file.open('rb')
    try:
        with zipfile.ZipFile(chapter.chapter_file, 'r') as archive:
            image_members = [
                name for name in archive.namelist()
                if not name.endswith('/') and os.path.splitext(name)[1].lower() in allowed_exts
            ]
            image_members.sort(key=lambda name: name.lower())

            for index, member_name in enumerate(image_members, start=1):
                data = archive.read(member_name)
                ext = os.path.splitext(member_name)[1].lower() or '.jpg'
                stored_name = f"chapter_{chapter.pk}_page_{index}{ext}"

                page = ChapterPage(chapter=chapter, page_number=index)
                page.image.save(stored_name, ContentFile(data), save=True)
                extracted += 1
    except zipfile.BadZipFile:
        extracted = 0
    finally:
        chapter.chapter_file.close()

    return extracted


INVOICE_TAX_RATE = Decimal('0.05')
INVOICE_SHIPPING_FEE = Decimal('49.00')


def build_invoice_totals(item_total, include_shipping=True):
    item_total = Decimal(item_total or 0).quantize(Decimal('0.01'))
    tax_amount = (item_total * INVOICE_TAX_RATE).quantize(Decimal('0.01'))
    shipping = INVOICE_SHIPPING_FEE if include_shipping else Decimal('0.00')
    grand_total = (item_total + tax_amount + shipping).quantize(Decimal('0.01'))
    return {
        'item_total': item_total,
        'tax_rate_percent': int(INVOICE_TAX_RATE * 100),
        'tax_amount': tax_amount,
        'shipping_fee': shipping,
        'grand_total': grand_total,
    }


# ═══════════════════════════════════════════════════════
# PUBLIC / GUEST VIEWS
# ═══════════════════════════════════════════════════════
def home(request):
    if request.user.is_authenticated and (request.user.is_staff or request.user.is_superuser):
        revenue_expr = ExpressionWrapper(
            F('quantity') * F('unit_price'),
            output_field=DecimalField(max_digits=12, decimal_places=2),
        )
        total_revenue = OrderItem.objects.aggregate(total=Sum(revenue_expr))['total'] or 0

        latest_orders = list(
            Order.objects.select_related('customer__user').order_by('-placed_at')[:5]
        )
        latest_chapters = list(
            Chapter.objects.select_related('digital_book').order_by('-upload_date')[:5]
        )
        recent_activity = []
        for order in latest_orders:
            recent_activity.append({
                'kind': 'Physical Order',
                'title': f"Order #{order.pk}",
                'detail': f"Customer: {order.customer.user.username} | Value: INR {order.total():.2f}",
                'timestamp': order.placed_at,
            })
        for chapter in latest_chapters:
            recent_activity.append({
                'kind': 'Digital Upload',
                'title': f"{chapter.digital_book.title} - Ch. {chapter.number}",
                'detail': f"Uploaded by admin panel | {chapter.pages.count()} pages",
                'timestamp': chapter.upload_date,
            })
        recent_activity.sort(key=lambda row: row['timestamp'], reverse=True)

        context = {
            'total_users': User.objects.count(),
            'total_customers': User.objects.filter(is_customer=True).count(),
            'active_sellers': SellerProfile.objects.filter(approved=True, user__is_active=True).count(),
            'pending_sellers': SellerProfile.objects.filter(approved=False).count(),
            'total_orders': Order.objects.count(),
            'total_revenue': total_revenue,
            'total_digital_chapters': Chapter.objects.count(),
            'physical_products': Product.objects.count(),
            'pending_actions_count': SellerProfile.objects.filter(approved=False).count(),
            'recent_activity': recent_activity,
        }
        return render(request, 'admin_panel/dashboard.html', context)

    if request.user.is_authenticated and request.user.is_seller:
        try:
            if request.user.seller_profile.approved:
                return redirect('seller_dashboard')
        except SellerProfile.DoesNotExist:
            pass

    latest_products = Product.objects.filter(stock__gt=0).order_by('-created_at')[:8]
    latest_digital_qs = DigitalBook.objects.order_by('-created_at', '-pk')
    latest_digital = latest_digital_qs[:10]
    # Spotlight always reflects the newest five digital books.
    spotlight_books = latest_digital_qs[:5]
    recent_reads = []
    if request.user.is_authenticated and request.user.is_customer:
        raw_recent_reads = list(
            RecentRead.objects
            .filter(customer__user=request.user)
            .select_related('digital_book', 'chapter')
            .order_by('-last_read_at')
        )

        # Keep only one entry per digital book (the latest chapter read) and preserve recency.
        seen_books = set()
        for entry in raw_recent_reads:
            if entry.digital_book_id in seen_books:
                continue
            seen_books.add(entry.digital_book_id)
            recent_reads.append(entry)
            if len(recent_reads) >= 8:
                break

        for entry in recent_reads:
            latest_chapter = entry.digital_book.chapters.order_by('-number').first()
            entry.latest_chapter = latest_chapter
            entry.has_new_chapter = bool(
                latest_chapter and latest_chapter.number > entry.chapter.number
            )
            entry.unread_count = (
                latest_chapter.number - entry.chapter.number
                if entry.has_new_chapter else 0
            )

    context = {
        'latest_products': latest_products,
        'latest_digital': latest_digital,
        'recent_reads': recent_reads,
    }
    context['spotlight_books'] = spotlight_books
    return render(request, 'home.html', context)


def product_catalog(request):
    products = (
        Product.objects
        .filter(stock__gt=0)
        .select_related('seller')
        .annotate(
            avg_rating=Avg('reviews__rating'),
            review_count=Count('reviews', distinct=True),
        )
    )
    all_product_titles = list(
        Product.objects.filter(stock__gt=0).values_list('title', flat=True)
    )
    query = request.GET.get('q', '')
    category = normalize_category_param(request.GET.get('category', ''))
    selected_sort = (request.GET.get('sort') or 'featured').strip().lower()

    sort_choices = [
        ('featured', 'Featured'),
        ('newest', 'Newest Arrivals'),
        ('price_low', 'Price: Low to High'),
        ('price_high', 'Price: High to Low'),
        ('top_rated', 'Top Rated'),
    ]
    valid_sorts = {key for key, _ in sort_choices}
    if selected_sort not in valid_sorts:
        selected_sort = 'featured'

    if query:
        products = products.filter(
            Q(title__icontains=query) | Q(description__icontains=query)
        )
    if category:
        products = products.filter(category=category)

    if selected_sort == 'price_low':
        products = products.order_by('price', '-created_at')
    elif selected_sort == 'price_high':
        products = products.order_by('-price', '-created_at')
    elif selected_sort == 'top_rated':
        products = products.order_by('-avg_rating', '-review_count', '-created_at')
    else:
        products = products.order_by('-created_at')

    return render(request, 'catalog/product_catalog.html', {
        'products': products,
        'all_product_titles': all_product_titles,
        'query': query,
        'selected_category': category,
        'selected_sort': selected_sort,
        'sort_choices': sort_choices,
        'categories': CategoryChoice.choices,
        'cart_count': cart_item_count(request),
    })


def product_detail(request, pk):
    product = get_object_or_404(
        Product.objects
        .select_related('seller')
        .annotate(
            avg_rating=Avg('reviews__rating'),
            review_count=Count('reviews', distinct=True),
        ),
        pk=pk,
    )
    preview_pages = product.preview_pages.all()
    reviews = product.reviews.select_related('customer__user').all()
    related_products = (
        Product.objects
        .filter(category=product.category, stock__gt=0)
        .exclude(pk=product.pk)
        .select_related('seller')
        .annotate(
            avg_rating=Avg('reviews__rating'),
            review_count=Count('reviews', distinct=True),
        )
        .order_by('-created_at')[:4]
    )
    review_form = ProductReviewForm()
    has_purchased = False
    if request.user.is_authenticated and request.user.is_customer:
        try:
            customer_profile = request.user.customer_profile
            has_purchased = OrderItem.objects.filter(
                order__customer=customer_profile,
                product=product,
            ).exists()
        except CustomerProfile.DoesNotExist:
            has_purchased = False

    return render(request, 'catalog/product_detail.html', {
        'product': product,
        'preview_pages': preview_pages,
        'reviews': reviews,
        'related_products': related_products,
        'review_form': review_form,
        'has_purchased': has_purchased,
        'cart_count': cart_item_count(request),
    })


@login_required
@customer_required
def add_product_review(request, pk):
    product = get_object_or_404(Product, pk=pk)
    customer_profile = request.user.customer_profile

    has_purchased = OrderItem.objects.filter(
        order__customer=customer_profile,
        product=product,
    ).exists()
    if not has_purchased:
        messages.error(request, "You can rate a book only after purchasing it.")
        return redirect('product_detail', pk=product.pk)

    if request.method != 'POST':
        return redirect('product_detail', pk=product.pk)

    form = ProductReviewForm(request.POST)
    if not form.is_valid():
        messages.error(request, "Please provide a valid rating and review.")
        return redirect('product_detail', pk=product.pk)

    ProductReview.objects.update_or_create(
        customer=customer_profile,
        product=product,
        defaults={
            'rating': form.cleaned_data['rating'],
            'comment': form.cleaned_data['comment'],
        }
    )
    messages.success(request, "Your review has been saved.")
    return redirect('product_detail', pk=product.pk)


@login_required
@customer_required
def customer_feedback(request):
    customer_profile = request.user.customer_profile
    form = CustomerFeedbackForm(request.POST or None)

    if request.method == 'POST' and form.is_valid():
        entry = form.save(commit=False)
        entry.customer = customer_profile
        entry.save()
        messages.success(request, "Your message has been sent to admin.")
        return redirect('customer_feedback')

    feedback_entries = CustomerFeedback.objects.filter(customer=customer_profile)
    return render(request, 'customer/feedback.html', {
        'form': form,
        'feedback_entries': feedback_entries,
        'cart_count': cart_item_count(request),
    })


def digital_catalog(request):
    books = DigitalBook.objects.all()
    all_book_titles = list(DigitalBook.objects.values_list('title', flat=True))
    query = request.GET.get('q', '')
    category = normalize_category_param(request.GET.get('category', ''))

    if query:
        books = books.filter(
            Q(title__icontains=query) | Q(description__icontains=query)
        )
    if category:
        books = books.filter(category=category)

    return render(request, 'catalog/digital_catalog.html', {
        'books': books,
        'all_book_titles': all_book_titles,
        'query': query,
        'selected_category': category,
        'categories': CategoryChoice.choices,
    })


def digital_book_detail(request, pk):
    book = get_object_or_404(DigitalBook, pk=pk)
    chapters = book.chapters.all()
    source = (request.GET.get('source') or '').strip().lower()
    from_home = source == 'home'
    return render(request, 'catalog/digital_book_detail.html', {
        'book': book,
        'chapters': chapters,
        'from_home': from_home,
    })


@login_required
def read_chapter(request, book_pk, num):
    book = get_object_or_404(DigitalBook, pk=book_pk)
    chapter = get_object_or_404(Chapter, digital_book=book, number=num)

    # Convert CBZ on first read so customers can scroll through pages in-browser.
    if chapter.chapter_file and chapter.file_extension() == 'cbz' and not chapter.pages.exists():
        extract_cbz_to_pages(chapter)

    pages = chapter.pages.all()
    chapter_file_ext = chapter.file_extension()
    prev_chapter = Chapter.objects.filter(digital_book=book, number=num - 1).first()
    next_chapter = Chapter.objects.filter(digital_book=book, number=num + 1).first()

    # Persist a lightweight continue-reading history for customers.
    if request.user.is_authenticated and request.user.is_customer:
        try:
            customer_profile = request.user.customer_profile
            existing_entries = RecentRead.objects.filter(
                customer=customer_profile,
                digital_book=book,
            ).order_by('-last_read_at')

            if existing_entries.exists():
                latest_entry = existing_entries.first()
                latest_entry.chapter = chapter
                latest_entry.save(update_fields=['chapter', 'last_read_at'])
                existing_entries.exclude(pk=latest_entry.pk).delete()
            else:
                RecentRead.objects.create(
                    customer=customer_profile,
                    digital_book=book,
                    chapter=chapter,
                )
        except CustomerProfile.DoesNotExist:
            pass

    return render(request, 'catalog/read_chapter.html', {
        'book': book,
        'chapter': chapter,
        'pages': pages,
        'chapter_file_ext': chapter_file_ext,
        'prev_chapter': prev_chapter,
        'next_chapter': next_chapter,
    })


@login_required
@customer_required
def download_chapter_pdf(request, book_pk, num):
    book = get_object_or_404(DigitalBook, pk=book_pk)
    chapter = get_object_or_404(Chapter, digital_book=book, number=num)
    filename = f"{book.title}_ch_{chapter.number}.pdf".replace(' ', '_')

    # If admin uploaded a PDF already, return it directly.
    if chapter.chapter_file and chapter.file_extension() == 'pdf':
        chapter.chapter_file.open('rb')
        response = FileResponse(chapter.chapter_file, content_type='application/pdf')
        response['Content-Disposition'] = f'attachment; filename="{filename}"'
        return response

    # If a CBZ was uploaded, extract pages on demand and generate PDF.
    if chapter.chapter_file and chapter.file_extension() == 'cbz' and not chapter.pages.exists():
        extract_cbz_to_pages(chapter)

    pages = chapter.pages.all()
    if not pages:
        messages.warning(request, "This chapter cannot be downloaded as PDF yet.")
        return redirect('read_chapter', book_pk=book.pk, num=chapter.number)

    response = HttpResponse(content_type='application/pdf')
    response['Content-Disposition'] = f'attachment; filename="{filename}"'

    pdf = canvas.Canvas(response, pagesize=A4)
    width, height = A4
    margin = 24

    for page in pages:
        try:
            page.image.open('rb')
            image_reader = ImageReader(page.image.file)
            image_width, image_height = image_reader.getSize()
            drawable_width = width - (margin * 2)
            drawable_height = height - (margin * 2)
            scale = min(drawable_width / image_width, drawable_height / image_height)
            render_w = image_width * scale
            render_h = image_height * scale
            x = (width - render_w) / 2
            y = (height - render_h) / 2

            pdf.drawImage(
                image_reader,
                x,
                y,
                width=render_w,
                height=render_h,
                preserveAspectRatio=True,
                anchor='c',
            )
            pdf.showPage()
        finally:
            page.image.close()

    pdf.save()
    return response


# ═══════════════════════════════════════════════════════
# AUTHENTICATION VIEWS
# ═══════════════════════════════════════════════════════
def register_choice(request):
    return render(request, 'auth/register.html')


def register_customer(request):
    if request.method == 'POST':
        form = CustomerRegistrationForm(request.POST)
        if form.is_valid():
            user = form.save()
            login(request, user)
            messages.success(request, "Welcome! Your account has been created.")
            return redirect('home')
    else:
        form = CustomerRegistrationForm()
    return render(request, 'auth/register_customer.html', {'form': form})


def register_seller(request):
    if request.method == 'POST':
        form = SellerRegistrationForm(request.POST, request.FILES)
        if form.is_valid():
            form.save()
            messages.info(
                request,
                "Registration submitted! Your account is pending Admin approval. "
                "You will be able to log in once approved."
            )
            return redirect('login')
    else:
        form = SellerRegistrationForm()
    return render(request, 'auth/register_seller.html', {'form': form})


@never_cache
@ensure_csrf_cookie
def login_view(request):
    if request.user.is_authenticated:
        return redirect('home')
    if request.method == 'POST':
        username = request.POST.get('username', '').strip()
        password = request.POST.get('password', '')
        user = authenticate(request, username=username, password=password)
        if user is not None:
            # Block unapproved sellers
            if user.is_seller:
                try:
                    if not user.seller_profile.approved:
                        messages.error(request, "Your seller account is pending Admin approval.")
                        return redirect('login')
                except SellerProfile.DoesNotExist:
                    pass
            login(request, user)
            messages.success(request, f"Welcome back, {user.first_name or user.username}!")
            return redirect('home')
        else:
            messages.error(request, "Invalid username or password.")

    showcase_cover_url = ''
    showcase_title = ''

    book_with_cover = (
        DigitalBook.objects
        .filter(cover_image__isnull=False)
        .exclude(cover_image='')
        .order_by('-created_at')
        .first()
    )
    if book_with_cover and book_with_cover.cover_image:
        showcase_cover_url = book_with_cover.cover_image.url
        showcase_title = book_with_cover.title
    else:
        product_with_cover = (
            Product.objects
            .filter(cover_image__isnull=False)
            .exclude(cover_image='')
            .order_by('-created_at')
            .first()
        )
        if product_with_cover and product_with_cover.cover_image:
            showcase_cover_url = product_with_cover.cover_image.url
            showcase_title = product_with_cover.title

    return render(request, 'auth/login.html', {
        'showcase_cover_url': showcase_cover_url,
        'showcase_title': showcase_title,
    })


def logout_view(request):
    logout(request)
    messages.success(request, "You have been logged out.")
    return redirect('home')


# ═══════════════════════════════════════════════════════
# CART & CHECKOUT (Customer)
# ═══════════════════════════════════════════════════════
@login_required
@customer_required
def cart_view(request):
    cart = get_cart(request)
    items = []
    total = 0
    for pid, qty in cart.items():
        try:
            product = Product.objects.get(pk=int(pid))
            subtotal = product.price * qty
            total += subtotal
            items.append({'product': product, 'quantity': qty, 'subtotal': subtotal})
        except Product.DoesNotExist:
            pass
    return render(request, 'customer/cart.html', {
        'items': items,
        'total': total,
        'cart_count': cart_item_count(request),
    })


@login_required
@customer_required
def add_to_cart(request, pk):
    product = get_object_or_404(Product, pk=pk, stock__gt=0)
    cart = get_cart(request)
    pid = str(pk)
    raw_qty = request.POST.get('quantity') or request.GET.get('quantity') or 1
    try:
        requested_qty = max(1, int(raw_qty))
    except (TypeError, ValueError):
        requested_qty = 1

    current_qty = cart.get(pid, 0)
    target_qty = min(current_qty + requested_qty, product.stock)

    if target_qty > current_qty:
        added_qty = target_qty - current_qty
        cart[pid] = target_qty
        save_cart(request, cart)
        if added_qty == 1:
            messages.success(request, f"'{product.title}' added to cart.")
        else:
            messages.success(request, f"'{product.title}' added to cart (x{added_qty}).")
    else:
        messages.warning(request, "Not enough stock available.")

    redirect_target = (
        request.POST.get('next')
        or request.GET.get('next')
        or request.META.get('HTTP_REFERER')
        or 'product_catalog'
    )
    return redirect(redirect_target)


@login_required
@customer_required
def remove_from_cart(request, pk):
    cart = get_cart(request)
    pid = str(pk)
    if pid in cart:
        del cart[pid]
        save_cart(request, cart)
        messages.success(request, "Item removed from cart.")
    return redirect('cart')


@login_required
@customer_required
def update_cart(request, pk):
    if request.method == 'POST':
        cart = get_cart(request)
        pid = str(pk)
        qty = int(request.POST.get('quantity', 1))
        product = get_object_or_404(Product, pk=pk)
        if qty < 1:
            cart.pop(pid, None)
        elif qty <= product.stock:
            cart[pid] = qty
        else:
            messages.warning(request, f"Only {product.stock} in stock.")
        save_cart(request, cart)
    return redirect('cart')


@login_required
@customer_required
def checkout(request):
    cart = get_cart(request)
    if not cart:
        messages.error(request, "Your cart is empty.")
        return redirect('cart')

    customer_profile = request.user.customer_profile
    form = CheckoutForm(request.POST or None)

    if request.method == 'POST' and form.is_valid():
        raw_payment_method = request.POST.get('payment_method', 'cod').strip().lower()
        payment_map = {
            'card': 'CARD',
            'upi': 'UPI',
            'cod': 'COD',
        }
        payment_method = payment_map.get(raw_payment_method, 'COD')

        order = Order.objects.create(
            customer=customer_profile,
            status='PENDING',
            payment_method=payment_method,
            shipping_address=form.cleaned_data['shipping_address']
        )
        for pid, qty in cart.items():
            try:
                product = Product.objects.get(pk=int(pid))
                if product.stock >= qty:
                    OrderItem.objects.create(
                        order=order,
                        product=product,
                        quantity=qty,
                        unit_price=product.price
                    )
                    product.stock -= qty
                    product.save()
            except Product.DoesNotExist:
                pass
        save_cart(request, {})
        messages.success(request, f"Order #{order.pk} placed successfully!")
        return redirect('order_bill', pk=order.pk)

    items = []
    total = 0
    for pid, qty in cart.items():
        try:
            product = Product.objects.get(pk=int(pid))
            subtotal = product.price * qty
            total += subtotal
            items.append({'product': product, 'quantity': qty, 'subtotal': subtotal})
        except Product.DoesNotExist:
            pass

    totals = build_invoice_totals(total, include_shipping=True)

    return render(request, 'customer/checkout.html', {
        'form': form,
        'items': items,
        'total': total,
        'totals': totals,
        'cart_count': cart_item_count(request),
    })


@login_required
@customer_required
def order_history(request):
    orders = Order.objects.filter(customer=request.user.customer_profile)
    return render(request, 'customer/order_history.html', {
        'orders': orders,
        'cart_count': cart_item_count(request),
    })


@login_required
@customer_required
def order_bill(request, pk):
    order = get_object_or_404(
        Order.objects.prefetch_related('items__product').select_related('customer__user'),
        pk=pk,
        customer=request.user.customer_profile,
    )
    item_total = sum((item.subtotal() for item in order.items.all()), Decimal('0.00'))
    totals = build_invoice_totals(item_total, include_shipping=True)
    invoice_no = order.invoice_number()
    return render(request, 'customer/bill.html', {
        'order': order,
        'totals': totals,
        'invoice_no': invoice_no,
        'cart_count': cart_item_count(request),
    })


@login_required
@customer_required
def order_bill_pdf(request, pk):
    order = get_object_or_404(
        Order.objects.prefetch_related('items__product').select_related('customer__user'),
        pk=pk,
        customer=request.user.customer_profile,
    )

    response = HttpResponse(content_type='application/pdf')
    response['Content-Disposition'] = f'attachment; filename="invoice_order_{order.pk}.pdf"'

    item_total = sum((item.subtotal() for item in order.items.all()), Decimal('0.00'))
    totals = build_invoice_totals(item_total, include_shipping=True)
    invoice_no = order.invoice_number()

    pdf = canvas.Canvas(response, pagesize=A4)
    width, height = A4
    y = height - 50

    pdf.setTitle(f"Invoice {invoice_no}")
    pdf.setFont('Helvetica-Bold', 16)
    pdf.drawString(40, y, 'ZENIN INVOICE')
    y -= 28

    pdf.setFont('Helvetica', 10)
    pdf.drawString(40, y, f"Invoice No: {invoice_no}")
    y -= 16
    pdf.drawString(40, y, f"Order ID: #{order.pk}")
    y -= 16
    pdf.drawString(40, y, f"Order Date: {order.placed_at.strftime('%d %b %Y %I:%M %p')}")
    y -= 16
    customer_name = order.customer.user.get_full_name() or order.customer.user.username
    pdf.drawString(40, y, f"Customer: {customer_name}")
    y -= 16
    pdf.drawString(40, y, f"Payment Mode: {order.get_payment_method_display()}")
    y -= 16
    pdf.drawString(40, y, f"Status: {order.get_status_display()}")
    y -= 24

    pdf.setFont('Helvetica-Bold', 10)
    pdf.drawString(40, y, 'Product')
    pdf.drawString(300, y, 'Unit Price')
    pdf.drawString(390, y, 'Qty')
    pdf.drawString(450, y, 'Subtotal')
    y -= 10
    pdf.line(40, y, width - 40, y)
    y -= 16

    pdf.setFont('Helvetica', 10)
    for item in order.items.all():
        if y < 80:
            pdf.showPage()
            y = height - 50
            pdf.setFont('Helvetica', 10)

        product_title = item.product.title
        if len(product_title) > 42:
            product_title = product_title[:39] + '...'

        pdf.drawString(40, y, product_title)
        pdf.drawString(300, y, f"INR {item.unit_price}")
        pdf.drawString(390, y, str(item.quantity))
        pdf.drawString(450, y, f"INR {item.subtotal()}")
        y -= 16

    y -= 8
    pdf.line(40, y, width - 40, y)
    y -= 18
    pdf.setFont('Helvetica', 10)
    pdf.drawString(320, y, 'Items Total:')
    pdf.drawString(450, y, f"INR {totals['item_total']}")
    y -= 16
    pdf.drawString(320, y, f"Tax ({totals['tax_rate_percent']}%):")
    pdf.drawString(450, y, f"INR {totals['tax_amount']}")
    y -= 16
    pdf.drawString(320, y, 'Delivery Charge:')
    pdf.drawString(450, y, f"INR {totals['shipping_fee']}")
    y -= 18
    pdf.setFont('Helvetica-Bold', 11)
    pdf.drawString(320, y, 'Grand Total:')
    pdf.drawString(450, y, f"INR {totals['grand_total']}")

    y -= 28
    pdf.setFont('Helvetica', 9)
    pdf.drawString(40, y, f"Shipping Address: {order.shipping_address}")

    pdf.showPage()
    pdf.save()
    return response


@login_required
@seller_required
def seller_order_bill_pdf(request, pk):
    seller = request.user.seller_profile
    order = get_object_or_404(
        Order.objects.prefetch_related('items__product').select_related('customer__user'),
        pk=pk,
    )
    seller_items = [item for item in order.items.all() if item.product.seller_id == seller.id]
    if not seller_items:
        raise Http404

    response = HttpResponse(content_type='application/pdf')
    response['Content-Disposition'] = f'attachment; filename="seller_invoice_order_{order.pk}.pdf"'

    item_total = sum((item.subtotal() for item in seller_items), Decimal('0.00'))
    totals = build_invoice_totals(item_total, include_shipping=False)
    invoice_no = order.invoice_number()

    pdf = canvas.Canvas(response, pagesize=A4)
    width, height = A4
    y = height - 50

    pdf.setTitle(f"Seller Invoice {invoice_no}")
    pdf.setFont('Helvetica-Bold', 16)
    pdf.drawString(40, y, 'ZENIN SELLER INVOICE')
    y -= 28

    pdf.setFont('Helvetica', 10)
    pdf.drawString(40, y, f"Invoice No: {invoice_no}")
    y -= 16
    pdf.drawString(40, y, f"Order ID: #{order.pk}")
    y -= 16
    pdf.drawString(40, y, f"Order Date: {order.placed_at.strftime('%d %b %Y %I:%M %p')}")
    y -= 16
    customer_name = order.customer.user.get_full_name() or order.customer.user.username
    pdf.drawString(40, y, f"Customer: {customer_name}")
    y -= 16
    pdf.drawString(40, y, f"Seller: {seller.shop_name}")
    y -= 16
    pdf.drawString(40, y, f"Payment Mode: {order.get_payment_method_display()}")
    y -= 24

    pdf.setFont('Helvetica-Bold', 10)
    pdf.drawString(40, y, 'Product')
    pdf.drawString(300, y, 'Unit Price')
    pdf.drawString(390, y, 'Qty')
    pdf.drawString(450, y, 'Subtotal')
    y -= 10
    pdf.line(40, y, width - 40, y)
    y -= 16

    pdf.setFont('Helvetica', 10)
    for item in seller_items:
        if y < 80:
            pdf.showPage()
            y = height - 50
            pdf.setFont('Helvetica', 10)

        product_title = item.product.title
        if len(product_title) > 42:
            product_title = product_title[:39] + '...'

        pdf.drawString(40, y, product_title)
        pdf.drawString(300, y, f"INR {item.unit_price}")
        pdf.drawString(390, y, str(item.quantity))
        pdf.drawString(450, y, f"INR {item.subtotal()}")
        y -= 16

    y -= 8
    pdf.line(40, y, width - 40, y)
    y -= 18
    pdf.setFont('Helvetica', 10)
    pdf.drawString(320, y, 'Items Total:')
    pdf.drawString(450, y, f"INR {totals['item_total']}")
    y -= 16
    pdf.drawString(320, y, f"Tax ({totals['tax_rate_percent']}%):")
    pdf.drawString(450, y, f"INR {totals['tax_amount']}")
    y -= 18
    pdf.setFont('Helvetica-Bold', 11)
    pdf.drawString(320, y, 'Seller Total:')
    pdf.drawString(450, y, f"INR {totals['grand_total']}")

    y -= 26
    pdf.setFont('Helvetica', 9)
    pdf.drawString(40, y, 'Shipping charges are collected and handled at platform order level.')

    pdf.showPage()
    pdf.save()
    return response


# ═══════════════════════════════════════════════════════
# SELLER VIEWS
# ═══════════════════════════════════════════════════════
@login_required
@seller_required
def seller_dashboard(request):
    seller = request.user.seller_profile
    total_products = seller.products.count()
    total_orders = OrderItem.objects.filter(product__seller=seller).values('order').distinct().count()
    now = timezone.now()
    monthly_items = OrderItem.objects.filter(
        product__seller=seller,
        order__placed_at__year=now.year,
        order__placed_at__month=now.month,
    )
    monthly_revenue = sum(item.subtotal() for item in monthly_items)
    monthly_sales = monthly_items.aggregate(total_qty=Sum('quantity'))['total_qty'] or 0
    listed_products = seller.products.order_by('-created_at')[:8]

    return render(request, 'seller/dashboard.html', {
        'seller': seller,
        'total_products': total_products,
        'total_orders': total_orders,
        'monthly_revenue': monthly_revenue,
        'monthly_sales': monthly_sales,
        'listed_products': listed_products,
    })


@login_required
@seller_required
def seller_products(request):
    seller = request.user.seller_profile
    products = seller.products.all()
    return render(request, 'seller/products.html', {
        'products': products,
        'seller': seller,
    })


@login_required
@seller_required
def product_create(request):
    form = ProductForm(request.POST or None, request.FILES or None)
    form.fields.pop('genres', None)
    preview_form = MultiProductPreviewUploadForm(request.POST or None, request.FILES or None)
    if form.is_valid() and preview_form.is_valid():
        product = form.save(commit=False)
        product.seller = request.user.seller_profile
        product.save()
        preview_images = request.FILES.getlist('preview_images')
        if preview_images:
            save_product_preview_pages(product, preview_images)
        messages.success(request, f"Product '{product.title}' added!")
        return redirect('seller_products')
    return render(request, 'seller/product_form.html', {
        'form': form,
        'preview_form': preview_form,
        'action': 'Add',
    })


@login_required
@seller_required
def product_edit(request, pk):
    product = get_object_or_404(Product, pk=pk, seller=request.user.seller_profile)
    form = ProductForm(request.POST or None, request.FILES or None, instance=product)
    form.fields.pop('genres', None)
    preview_form = MultiProductPreviewUploadForm(request.POST or None, request.FILES or None)
    if form.is_valid() and preview_form.is_valid():
        form.save()
        preview_images = request.FILES.getlist('preview_images')
        reset_existing = bool(request.POST.get('replace_previews'))
        if preview_images:
            save_product_preview_pages(product, preview_images, reset_existing=reset_existing)
        messages.success(request, "Product updated!")
        return redirect('seller_products')
    return render(request, 'seller/product_form.html', {
        'form': form,
        'preview_form': preview_form,
        'action': 'Edit',
        'product': product,
    })


@login_required
@seller_required
def product_delete(request, pk):
    product = get_object_or_404(Product, pk=pk, seller=request.user.seller_profile)
    if request.method == 'POST':
        product.delete()
        messages.success(request, "Product deleted.")
        return redirect('seller_products')
    return render(request, 'seller/product_confirm_delete.html', {'product': product})


@login_required
@seller_required
def seller_orders(request):
    seller = request.user.seller_profile
    order_items = OrderItem.objects.filter(product__seller=seller).select_related(
        'order', 'order__customer__user', 'product'
    ).order_by('-order__placed_at')
    return render(request, 'seller/orders.html', {'order_items': order_items})


@login_required
@seller_required
def seller_order_update(request, pk):
    order = get_object_or_404(Order, pk=pk)
    if not OrderItem.objects.filter(order=order, product__seller=request.user.seller_profile).exists():
        raise Http404
    if request.method == 'POST':
        new_status = request.POST.get('status')
        valid = [s[0] for s in Order.STATUS_CHOICES]
        if new_status in valid:
            order.status = new_status
            order.save()
            messages.success(request, f"Order #{order.pk} status updated to {new_status}.")
    return redirect('seller_orders')


# ═══════════════════════════════════════════════════════
# ADMIN / SUPERUSER VIEWS
# ═══════════════════════════════════════════════════════
@login_required
@admin_required
def admin_seller_requests(request):
    pending = SellerProfile.objects.filter(approved=False).select_related('user')
    approved = SellerProfile.objects.filter(approved=True).select_related('user')
    return render(request, 'admin_panel/seller_requests.html', {
        'pending': pending,
        'approved': approved,
    })


@login_required
@admin_required
def approve_seller(request, pk):
    profile = get_object_or_404(SellerProfile, pk=pk)
    if request.method == 'POST':
        profile.approved = True
        profile.save()
        messages.success(request, f"Seller '{profile.user.username}' approved.")
    return redirect('admin_seller_requests')


@login_required
@admin_required
def reject_seller(request, pk):
    profile = get_object_or_404(SellerProfile, pk=pk)
    if request.method == 'POST':
        user = profile.user
        profile.delete()
        user.delete()
        messages.success(request, "Seller request rejected and account removed.")
    return redirect('admin_seller_requests')


@login_required
@admin_required
def admin_manage_sellers(request):
    revenue_expr = ExpressionWrapper(
        F('products__orderitem__quantity') * F('products__orderitem__unit_price'),
        output_field=DecimalField(max_digits=12, decimal_places=2),
    )
    sellers = (
        SellerProfile.objects
        .filter(approved=True)
        .select_related('user')
        .annotate(total_products=Count('products', distinct=True))
        .annotate(total_orders=Count('products__orderitem__order', distinct=True))
        .annotate(total_sales=Sum(revenue_expr))
        .order_by('shop_name')
    )
    return render(request, 'admin_panel/manage_sellers.html', {'sellers': sellers})


@login_required
@admin_required
def toggle_seller_status(request, pk):
    profile = get_object_or_404(SellerProfile.objects.select_related('user'), pk=pk, approved=True)
    if request.method == 'POST':
        user = profile.user
        user.is_active = not user.is_active
        user.save(update_fields=['is_active'])
        state = 'activated' if user.is_active else 'suspended'
        messages.success(request, f"Seller '{user.username}' has been {state}.")
    return redirect('admin_manage_sellers')


@login_required
@admin_required
def admin_manage_customers(request):
    spend_expr = ExpressionWrapper(
        F('orders__items__quantity') * F('orders__items__unit_price'),
        output_field=DecimalField(max_digits=12, decimal_places=2),
    )
    customers = (
        CustomerProfile.objects
        .select_related('user')
        .annotate(order_count=Count('orders', distinct=True))
        .annotate(total_spent=Sum(spend_expr))
        .order_by('user__username')
    )
    return render(request, 'admin_panel/manage_customers.html', {'customers': customers})


@login_required
@admin_required
def toggle_customer_status(request, pk):
    customer = get_object_or_404(CustomerProfile.objects.select_related('user'), pk=pk)
    if request.method == 'POST':
        user = customer.user
        user.is_active = not user.is_active
        user.save(update_fields=['is_active'])
        state = 'activated' if user.is_active else 'deactivated'
        messages.success(request, f"Customer '{user.username}' has been {state}.")
    return redirect('admin_manage_customers')


@login_required
@admin_required
def customer_purchase_history(request, pk):
    customer = get_object_or_404(CustomerProfile.objects.select_related('user'), pk=pk)
    orders = (
        Order.objects
        .filter(customer=customer)
        .prefetch_related('items__product')
        .order_by('-placed_at')
    )
    return render(request, 'admin_panel/customer_purchase_history.html', {
        'customer': customer,
        'orders': orders,
    })


@login_required
@admin_required
def monthly_report(request):
    from django.db.models.functions import TruncMonth
    from django.db.models import Count

    data = (
        Order.objects
        .annotate(month=TruncMonth('placed_at'))
        .values('month')
        .annotate(total_orders=Count('id'))
        .order_by('-month')
    )

    report_rows = []
    for row in data:
        month_orders = Order.objects.filter(
            placed_at__year=row['month'].year,
            placed_at__month=row['month'].month
        )
        revenue = sum(
            sum(item.subtotal() for item in o.items.all())
            for o in month_orders
        )
        active_sellers = (
            OrderItem.objects
            .filter(order__in=month_orders)
            .values('product__seller').distinct().count()
        )
        report_rows.append({
            'month': row['month'],
            'total_orders': row['total_orders'],
            'total_revenue': revenue,
            'active_sellers': active_sellers,
            'year': row['month'].year,
            'month_number': row['month'].month,
        })

    return render(request, 'admin_panel/monthly_report.html', {'report_rows': report_rows})


@login_required
@admin_required
def admin_reporting_dashboard(request):
    sales_expr = ExpressionWrapper(
        F('quantity') * F('unit_price'),
        output_field=DecimalField(max_digits=12, decimal_places=2),
    )

    # 1) Sales & Revenue Reports
    monthly_sales = list(
        OrderItem.objects
        .annotate(month=TruncMonth('order__placed_at'))
        .values('month')
        .annotate(
            total_revenue=Sum(sales_expr),
            total_orders=Count('order', distinct=True),
        )
        .order_by('-month')[:12]
    )
    for row in monthly_sales:
        row['commission_fee'] = (row['total_revenue'] or Decimal('0.00')) * Decimal('0.10')

    top_products = list(
        OrderItem.objects
        .values('product__title', 'product__category')
        .annotate(
            total_quantity=Sum('quantity'),
            total_revenue=Sum(sales_expr),
        )
        .order_by('-total_quantity', '-total_revenue')[:5]
    )

    seller_revenue = list(
        SellerProfile.objects
        .filter(approved=True)
        .select_related('user')
        .annotate(
            total_earnings=Sum(
                ExpressionWrapper(
                    F('products__orderitem__quantity') * F('products__orderitem__unit_price'),
                    output_field=DecimalField(max_digits=12, decimal_places=2),
                )
            ),
            total_units=Sum('products__orderitem__quantity'),
            total_orders=Count('products__orderitem__order', distinct=True),
        )
        .order_by('-total_earnings', 'shop_name')
    )

    status_counts_raw = (
        Order.objects
        .values('status')
        .annotate(total=Count('id'))
    )
    status_map = {row['status']: row['total'] for row in status_counts_raw}
    order_status_report = [
        {
            'status_key': key,
            'status_label': label,
            'total': status_map.get(key, 0),
        }
        for key, label in Order.STATUS_CHOICES
    ]

    # 2) User & Content Analytics
    most_read_titles = list(
        RecentRead.objects
        .values('digital_book__title', 'digital_book__category')
        .annotate(read_count=Count('id'))
        .order_by('-read_count', 'digital_book__title')[:10]
    )

    weekly_registrations = list(
        User.objects
        .annotate(week=TruncWeek('date_joined'))
        .values('week')
        .annotate(
            customer_count=Count('id', filter=Q(is_customer=True)),
            seller_count=Count('id', filter=Q(is_seller=True)),
            total_count=Count('id'),
        )
        .order_by('-week')[:12]
    )

    chapter_upload_history = list(
        Chapter.objects
        .select_related('digital_book')
        .order_by('-upload_date')[:15]
    )

    genre_popularity = []
    for genre in Genre.objects.all():
        purchase_count = (
            OrderItem.objects
            .filter(product__genres=genre)
            .aggregate(total=Sum('quantity'))
            .get('total')
        ) or 0
        read_count = RecentRead.objects.filter(digital_book__genres=genre).count()

        genre_popularity.append({
            'genre_key': genre.slug,
            'genre_label': genre.name,
            'purchase_count': purchase_count,
            'read_count': read_count,
            'combined_total': purchase_count + read_count,
        })

    if not genre_popularity:
        for key, label in CategoryChoice.choices:
            purchase_count = (
                OrderItem.objects
                .filter(product__category=key)
                .aggregate(total=Sum('quantity'))
                .get('total')
            ) or 0
            read_count = RecentRead.objects.filter(digital_book__category=key).count()
            genre_popularity.append({
                'genre_key': key,
                'genre_label': label,
                'purchase_count': purchase_count,
                'read_count': read_count,
                'combined_total': purchase_count + read_count,
            })

    genre_popularity.sort(key=lambda row: row['combined_total'], reverse=True)

    # 3) Operational & Management Reports
    pending_seller_approvals = list(
        SellerProfile.objects
        .filter(approved=False)
        .select_related('user')
        .order_by('-created_at')
    )

    low_stock_alerts = list(
        Product.objects
        .filter(stock__lt=5)
        .select_related('seller__user')
        .order_by('stock', 'title')
    )

    feedback_available = True
    feedback_log = list(
        ProductReview.objects
        .select_related('product', 'customer__user')
        .order_by('-created_at')[:10]
    )
    feedback_average = ProductReview.objects.aggregate(avg=Avg('rating')).get('avg')

    total_revenue = OrderItem.objects.aggregate(total=Sum(sales_expr)).get('total') or Decimal('0.00')
    total_orders = Order.objects.count()
    total_users = User.objects.count()
    total_books = DigitalBook.objects.count()

    context = {
        'total_revenue': total_revenue,
        'total_orders': total_orders,
        'total_users': total_users,
        'total_books': total_books,
        'monthly_sales': monthly_sales,
        'top_products': top_products,
        'seller_revenue': seller_revenue,
        'order_status_report': order_status_report,
        'most_read_titles': most_read_titles,
        'weekly_registrations': weekly_registrations,
        'chapter_upload_history': chapter_upload_history,
        'genre_popularity': genre_popularity,
        'pending_seller_approvals': pending_seller_approvals,
        'low_stock_alerts': low_stock_alerts,
        'feedback_available': feedback_available,
        'feedback_log': feedback_log,
        'feedback_average': feedback_average,
    }
    return render(request, 'admin_panel/report_dashboard.html', context)


@login_required
@admin_required
def admin_customer_feedbacks(request):
    feedback_entries = (
        CustomerFeedback.objects
        .select_related('customer__user')
        .order_by('-created_at')
    )
    return render(request, 'admin_panel/customer_feedbacks.html', {
        'feedback_entries': feedback_entries,
        'status_choices': CustomerFeedback.STATUS_CHOICES,
    })


@login_required
@admin_required
def admin_feedback_reply(request, pk):
    entry = get_object_or_404(
        CustomerFeedback.objects.select_related('customer__user'),
        pk=pk,
    )

    if request.method == 'POST':
        status = request.POST.get('status', '').strip()
        admin_reply = request.POST.get('admin_reply', '').strip()
        valid_statuses = {key for key, _ in CustomerFeedback.STATUS_CHOICES}

        if not admin_reply:
            messages.error(request, "Please enter a reply before saving.")
            return render(request, 'admin_panel/customer_feedback_reply.html', {
                'entry': entry,
                'status_choices': CustomerFeedback.STATUS_CHOICES,
            })

        if status and status in valid_statuses:
            entry.status = status
        elif entry.status == 'OPEN':
            entry.status = 'IN_REVIEW'

        entry.admin_note = admin_reply
        entry.save(update_fields=['status', 'admin_note', 'updated_at'])
        messages.success(request, "Reply saved and feedback updated.")
        return redirect('admin_feedback_reply', pk=entry.pk)

    return render(request, 'admin_panel/customer_feedback_reply.html', {
        'entry': entry,
        'status_choices': CustomerFeedback.STATUS_CHOICES,
    })


@login_required
@admin_required
def admin_update_feedback_status(request, pk):
    entry = get_object_or_404(CustomerFeedback, pk=pk)
    if request.method == 'POST':
        status = request.POST.get('status', '').strip()
        admin_note = request.POST.get('admin_note', '').strip()
        valid_statuses = {key for key, _ in CustomerFeedback.STATUS_CHOICES}
        if status in valid_statuses:
            entry.status = status
            entry.admin_note = admin_note
            entry.save(update_fields=['status', 'admin_note', 'updated_at'])
            messages.success(request, "Feedback status updated.")
        else:
            messages.error(request, "Invalid status selected.")
    return redirect('admin_customer_feedbacks')


@login_required
@admin_required
def download_monthly_sales(request, year, month):
    if month < 1 or month > 12:
        raise Http404

    sales_expr = ExpressionWrapper(
        F('quantity') * F('unit_price'),
        output_field=DecimalField(max_digits=12, decimal_places=2),
    )

    items = (
        OrderItem.objects
        .filter(order__placed_at__year=year, order__placed_at__month=month)
        .values(
            'product__seller__shop_name',
            'product__seller__user__username',
            'product__seller__user__email',
            'product__title',
        )
        .annotate(total_books_sold=Sum('quantity'))
        .annotate(total_earning=Sum(sales_expr))
        .order_by('product__seller__shop_name', 'product__title')
    )

    filename = f"monthly_sales_{year}_{month:02d}.csv"
    response = HttpResponse(content_type='text/csv')
    response['Content-Disposition'] = f'attachment; filename="{filename}"'

    writer = csv.writer(response)
    writer.writerow(['Month', f"{calendar.month_name[month]} {year}"])
    writer.writerow([])
    writer.writerow([
        'Seller Shop',
        'Seller Username',
        'Seller Email',
        'Book Title',
        'Books Sold',
        'Earning Per Book (Unit Price)',
        'Total Earning (Book Sales)',
    ])

    if not items:
        writer.writerow(['No sales data found for this month'])
        return response

    for row in items:
        books_sold = row['total_books_sold'] or 0
        total_earning = row['total_earning'] or Decimal('0.00')
        unit_earning = (total_earning / books_sold) if books_sold else Decimal('0.00')
        writer.writerow([
            row['product__seller__shop_name'] or '-',
            row['product__seller__user__username'] or '-',
            row['product__seller__user__email'] or '-',
            row['product__title'],
            books_sold,
            f"{unit_earning:.2f}",
            f"{total_earning:.2f}",
        ])

    return response


@login_required
@admin_required
def admin_digital_books(request):
    books = DigitalBook.objects.all()
    query = request.GET.get('q', '').strip()
    category = normalize_category_param(request.GET.get('category', ''))

    if query:
        books = books.filter(
            Q(title__icontains=query) | Q(description__icontains=query)
        )
    if category:
        books = books.filter(category=category)

    return render(request, 'admin_panel/digital_books.html', {
        'books': books,
        'query': query,
        'selected_category': category,
        'categories': CategoryChoice.choices,
    })


@login_required
@admin_required
def digital_book_create(request):
    form = DigitalBookForm(request.POST or None, request.FILES or None)
    if form.is_valid():
        book = form.save()
        messages.success(request, f"Digital book '{book.title}' created.")
        return redirect('admin_digital_books')
    return render(request, 'admin_panel/digital_book_form.html', {'form': form, 'action': 'Create'})


@login_required
@admin_required
def digital_book_edit(request, pk):
    book = get_object_or_404(DigitalBook, pk=pk)
    form = DigitalBookForm(request.POST or None, request.FILES or None, instance=book)
    if form.is_valid():
        form.save()
        messages.success(request, "Digital book updated.")
        return redirect('admin_digital_books')
    return render(request, 'admin_panel/digital_book_form.html', {'form': form, 'action': 'Edit', 'book': book})


@login_required
@admin_required
def digital_book_delete(request, pk):
    book = get_object_or_404(DigitalBook, pk=pk)
    if request.method == 'POST':
        book.delete()
        messages.success(request, "Digital book deleted.")
        return redirect('admin_digital_books')
    return render(request, 'admin_panel/digital_book_confirm_delete.html', {'book': book})


@login_required
@admin_required
def chapter_list(request, book_pk):
    book = get_object_or_404(DigitalBook, pk=book_pk)
    chapters = book.chapters.all()
    return render(request, 'admin_panel/chapters.html', {'book': book, 'chapters': chapters})


@login_required
@admin_required
def chapter_create(request, book_pk):
    book = get_object_or_404(DigitalBook, pk=book_pk)
    chapter_form = ChapterForm(request.POST or None)
    page_form = MultiPageUploadForm(request.POST or None, request.FILES or None)

    if request.method == 'POST' and chapter_form.is_valid() and page_form.is_valid():
        images = request.FILES.getlist('images')
        chapter_file = page_form.cleaned_data.get('chapter_file')

        if not images and not chapter_file:
            messages.error(request, "Upload either chapter page images or one PDF/CBZ file.")
            return render(request, 'admin_panel/chapter_form.html', {
                'book': book,
                'chapter_form': chapter_form,
                'page_form': page_form,
                'action': 'Add',
            })

        if images and chapter_file:
            messages.error(request, "Please upload either images or a PDF/CBZ file, not both.")
            return render(request, 'admin_panel/chapter_form.html', {
                'book': book,
                'chapter_form': chapter_form,
                'page_form': page_form,
                'action': 'Add',
            })

        chapter = chapter_form.save(commit=False)
        chapter.digital_book = book
        chapter.chapter_file = chapter_file
        chapter.save()

        for i, img in enumerate(images, start=1):
            ChapterPage.objects.create(chapter=chapter, page_number=i, image=img)

        extracted_pages = 0
        if chapter_file and chapter.file_extension() == 'cbz':
            extracted_pages = extract_cbz_to_pages(chapter)

        if chapter_file:
            if chapter.file_extension() == 'cbz':
                messages.success(request, f"Chapter {chapter.number} uploaded as CBZ and extracted into {extracted_pages} scrollable pages.")
            else:
                messages.success(request, f"Chapter {chapter.number} uploaded as {chapter.file_extension().upper()} file.")
        else:
            messages.success(request, f"Chapter {chapter.number} uploaded with {len(images)} pages.")
        return redirect('chapter_list', book_pk=book.pk)

    return render(request, 'admin_panel/chapter_form.html', {
        'book': book,
        'chapter_form': chapter_form,
        'page_form': page_form,
        'action': 'Add',
    })


@login_required
@admin_required
def chapter_bulk_upload(request, book_pk):
    book = get_object_or_404(DigitalBook, pk=book_pk)
    form = BulkChapterUploadForm(request.POST or None, request.FILES or None)

    if request.method == 'POST' and form.is_valid():
        files = form.cleaned_data.get('chapter_files') or []
        existing_numbers = set(book.chapters.values_list('number', flat=True))
        next_number = (max(existing_numbers) + 1) if existing_numbers else 1
        used_numbers = set()

        created_count = 0
        extracted_count = 0

        for uploaded_file in files:
            base_name = os.path.splitext(uploaded_file.name)[0]
            match = re.search(r'(\d+)', base_name)
            proposed_number = int(match.group(1)) if match else next_number

            if proposed_number < 1:
                proposed_number = next_number

            while proposed_number in existing_numbers or proposed_number in used_numbers:
                proposed_number += 1

            chapter = Chapter.objects.create(
                digital_book=book,
                number=proposed_number,
                title=f"Chapter {proposed_number}",
                chapter_file=uploaded_file,
            )

            if chapter.file_extension() == 'cbz':
                extracted_count += extract_cbz_to_pages(chapter)

            created_count += 1
            used_numbers.add(proposed_number)
            next_number = max(next_number, proposed_number + 1)

        messages.success(
            request,
            f"{created_count} chapters uploaded successfully. "
            f"Titles were set from chapter numbers (Chapter N)."
        )
        if extracted_count:
            messages.info(request, f"Extracted {extracted_count} pages from uploaded CBZ files.")
        return redirect('chapter_list', book_pk=book.pk)

    return render(request, 'admin_panel/chapter_bulk_form.html', {
        'book': book,
        'form': form,
    })


@login_required
@admin_required
def chapter_delete(request, book_pk, num):
    book = get_object_or_404(DigitalBook, pk=book_pk)
    chapter = get_object_or_404(Chapter, digital_book=book, number=num)
    if request.method == 'POST':
        chapter.delete()
        messages.success(request, f"Chapter {num} deleted.")
        return redirect('chapter_list', book_pk=book.pk)
    return render(request, 'admin_panel/chapter_confirm_delete.html', {'chapter': chapter, 'book': book})

