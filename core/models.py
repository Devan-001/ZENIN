from django.contrib.auth.models import AbstractUser
from django.db import models
from django.utils import timezone


# ─────────────────────────────────────────
# 1. Custom User
# ─────────────────────────────────────────
class User(AbstractUser):
    is_seller = models.BooleanField(default=False)
    is_customer = models.BooleanField(default=False)

    def __str__(self):
        return self.username


# ─────────────────────────────────────────
# 2. Role Profiles
# ─────────────────────────────────────────
class SellerProfile(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='seller_profile')
    shop_name = models.CharField(max_length=200)
    phone_number = models.CharField(max_length=10, blank=True)
    seller_license = models.FileField(upload_to='seller_licenses/', blank=True, null=True)
    approved = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.shop_name} ({'Approved' if self.approved else 'Pending'})"


class CustomerProfile(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='customer_profile')
    phone_number = models.CharField(max_length=10, blank=True)
    joined_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.user.username


# ─────────────────────────────────────────
# 3. Category choices (shared)
# ─────────────────────────────────────────
class CategoryChoice(models.TextChoices):
    MANGA = 'MANGA', 'Manga'
    MANHWA = 'MANHWA', 'Manhwa'
    COMIC = 'COMIC', 'Comic'


class Genre(models.Model):
    name = models.CharField(max_length=80, unique=True)
    slug = models.SlugField(max_length=100, unique=True)

    class Meta:
        ordering = ['name']

    def __str__(self):
        return self.name


# ─────────────────────────────────────────
# 4. Physical Products (E-commerce)
# ─────────────────────────────────────────
class Product(models.Model):
    seller = models.ForeignKey(SellerProfile, on_delete=models.CASCADE, related_name='products')
    title = models.CharField(max_length=255)
    category = models.CharField(max_length=10, choices=CategoryChoice.choices)
    genres = models.ManyToManyField(Genre, related_name='products', blank=True)
    description = models.TextField(blank=True)
    price = models.DecimalField(max_digits=8, decimal_places=2)
    stock = models.PositiveIntegerField(default=0)
    cover_image = models.ImageField(upload_to='product_covers/', blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.title} (₹{self.price})"


class ProductPreviewPage(models.Model):
    product = models.ForeignKey(Product, on_delete=models.CASCADE, related_name='preview_pages')
    page_number = models.PositiveIntegerField()
    image = models.ImageField(upload_to='product_preview_pages/')

    class Meta:
        unique_together = ('product', 'page_number')
        ordering = ['page_number']

    def __str__(self):
        return f"{self.product.title} - Preview Page {self.page_number}"


# ─────────────────────────────────────────
# 5. Digital Books & Chapters
# ─────────────────────────────────────────
class DigitalBook(models.Model):
    title = models.CharField(max_length=255)
    category = models.CharField(max_length=10, choices=CategoryChoice.choices)
    genres = models.ManyToManyField(Genre, related_name='digital_books', blank=True)
    description = models.TextField(blank=True)
    cover_image = models.ImageField(upload_to='digital_covers/', blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['title']

    def __str__(self):
        return self.title

    def chapter_count(self):
        return self.chapters.count()


class Chapter(models.Model):
    digital_book = models.ForeignKey(DigitalBook, on_delete=models.CASCADE, related_name='chapters')
    number = models.PositiveIntegerField()
    title = models.CharField(max_length=255, blank=True)
    upload_date = models.DateTimeField(default=timezone.now)
    # Admin can upload either page images or a single PDF/CBZ file.
    chapter_file = models.FileField(upload_to='chapter_files/', blank=True, null=True)
    
    class Meta:
        unique_together = ('digital_book', 'number')
        ordering = ['number']

    def __str__(self):
        return f"{self.digital_book.title} – Ch. {self.number}"

    def has_page_images(self):
        return self.pages.exists()

    def file_extension(self):
        if not self.chapter_file:
            return ''
        return self.chapter_file.name.rsplit('.', 1)[-1].lower()


class ChapterPage(models.Model):
    chapter = models.ForeignKey(Chapter, on_delete=models.CASCADE, related_name='pages')
    page_number = models.PositiveIntegerField()
    image = models.ImageField(upload_to='chapter_pages/')

    class Meta:
        unique_together = ('chapter', 'page_number')
        ordering = ['page_number']

    def __str__(self):
        return f"Ch.{self.chapter.number} – Page {self.page_number}"


class RecentRead(models.Model):
    customer = models.ForeignKey(CustomerProfile, on_delete=models.CASCADE, related_name='recent_reads')
    digital_book = models.ForeignKey(DigitalBook, on_delete=models.CASCADE, related_name='recent_reads')
    chapter = models.ForeignKey(Chapter, on_delete=models.CASCADE, related_name='recent_reads')
    last_read_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-last_read_at']
        unique_together = ('customer', 'chapter')

    def __str__(self):
        return f"{self.customer.user.username} - {self.digital_book.title} Ch. {self.chapter.number}"


# ─────────────────────────────────────────
# 6. Orders & Cart
# ─────────────────────────────────────────
class Order(models.Model):
    STATUS_CHOICES = [
        ('PENDING', 'Pending'),
        ('PROCESSING', 'Processing'),
        ('SHIPPED', 'Shipped'),
        ('COMPLETED', 'Completed'),
        ('CANCELLED', 'Cancelled'),
    ]
    PAYMENT_METHOD_CHOICES = [
        ('CARD', 'Prepaid (Card)'),
        ('UPI', 'Prepaid (UPI)'),
        ('COD', 'Cash on Delivery'),
    ]
    customer = models.ForeignKey(CustomerProfile, on_delete=models.CASCADE, related_name='orders')
    placed_at = models.DateTimeField(auto_now_add=True)
    status = models.CharField(max_length=12, choices=STATUS_CHOICES, default='PENDING')
    payment_method = models.CharField(max_length=10, choices=PAYMENT_METHOD_CHOICES, default='COD')
    shipping_address = models.TextField(blank=True)

    class Meta:
        ordering = ['-placed_at']

    def __str__(self):
        return f"Order #{self.pk} by {self.customer.user.username}"

    def total(self):
        return sum(item.subtotal() for item in self.items.all())

    def is_prepaid(self):
        return self.payment_method in {'CARD', 'UPI'}

    def invoice_number(self):
        year = self.placed_at.year if self.placed_at else timezone.now().year
        return f"ZEN-{year}-{self.pk:06d}"


class OrderItem(models.Model):
    order = models.ForeignKey(Order, on_delete=models.CASCADE, related_name='items')
    product = models.ForeignKey(Product, on_delete=models.PROTECT)
    quantity = models.PositiveIntegerField(default=1)
    unit_price = models.DecimalField(max_digits=8, decimal_places=2)

    class Meta:
        unique_together = ('order', 'product')

    def subtotal(self):
        return self.unit_price * self.quantity

    def __str__(self):
        return f"{self.quantity}× {self.product.title}"


class ProductReview(models.Model):
    customer = models.ForeignKey(CustomerProfile, on_delete=models.CASCADE, related_name='product_reviews')
    product = models.ForeignKey(Product, on_delete=models.CASCADE, related_name='reviews')
    rating = models.PositiveSmallIntegerField()
    comment = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']
        unique_together = ('customer', 'product')

    def __str__(self):
        return f"{self.product.title} review by {self.customer.user.username}"


class CustomerFeedback(models.Model):
    TYPE_CHOICES = [
        ('FEEDBACK', 'Feedback'),
        ('COMPLAINT', 'Complaint'),
    ]
    STATUS_CHOICES = [
        ('OPEN', 'Open'),
        ('IN_REVIEW', 'In Review'),
        ('RESOLVED', 'Resolved'),
    ]

    customer = models.ForeignKey(CustomerProfile, on_delete=models.CASCADE, related_name='feedback_entries')
    feedback_type = models.CharField(max_length=12, choices=TYPE_CHOICES, default='FEEDBACK')
    subject = models.CharField(max_length=180)
    message = models.TextField()
    status = models.CharField(max_length=12, choices=STATUS_CHOICES, default='OPEN')
    admin_note = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.get_feedback_type_display()} by {self.customer.user.username}: {self.subject}"

