from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from django.utils.html import format_html
from .models import (
    User, SellerProfile, CustomerProfile,
    Product, ProductPreviewPage, DigitalBook, Chapter, ChapterPage,
    Order, OrderItem, RecentRead, Genre, ProductReview
)


@admin.register(User)
class UserAdmin(BaseUserAdmin):
    list_display = ['username', 'email', 'is_seller', 'is_customer', 'is_staff']
    fieldsets = BaseUserAdmin.fieldsets + (
        ('Role Flags', {'fields': ('is_seller', 'is_customer')}),
    )


@admin.register(SellerProfile)
class SellerProfileAdmin(admin.ModelAdmin):
    list_display = ['shop_name', 'user', 'approved', 'created_at', 'seller_license_link']
    list_filter = ['approved']
    readonly_fields = ['seller_license_link']
    actions = ['approve_sellers']

    def seller_license_link(self, obj):
        if obj.seller_license:
            return format_html('<a href="{}" target="_blank" rel="noopener">View License</a>', obj.seller_license.url)
        return '-'
    seller_license_link.short_description = 'Seller License'

    def approve_sellers(self, request, queryset):
        queryset.update(approved=True)
    approve_sellers.short_description = "Approve selected sellers"


@admin.register(CustomerProfile)
class CustomerProfileAdmin(admin.ModelAdmin):
    list_display = ['user', 'joined_at']


class OrderItemInline(admin.TabularInline):
    model = OrderItem
    extra = 0
    readonly_fields = ['unit_price']


@admin.register(Order)
class OrderAdmin(admin.ModelAdmin):
    list_display = ['id', 'customer', 'status', 'placed_at']
    list_filter = ['status']
    inlines = [OrderItemInline]


class ChapterPageInline(admin.TabularInline):
    model = ChapterPage
    extra = 1


class ProductPreviewPageInline(admin.TabularInline):
    model = ProductPreviewPage
    extra = 1


@admin.register(Chapter)
class ChapterAdmin(admin.ModelAdmin):
    list_display = ['digital_book', 'number', 'title', 'upload_date']
    inlines = [ChapterPageInline]


@admin.register(DigitalBook)
class DigitalBookAdmin(admin.ModelAdmin):
    list_display = ['title', 'category', 'chapter_count', 'created_at']
    list_filter = ['category']
    filter_horizontal = ['genres']


@admin.register(Product)
class ProductAdmin(admin.ModelAdmin):
    list_display = ['title', 'seller', 'category', 'price', 'stock', 'created_at']
    list_filter = ['category']
    inlines = [ProductPreviewPageInline]
    filter_horizontal = ['genres']


@admin.register(ProductPreviewPage)
class ProductPreviewPageAdmin(admin.ModelAdmin):
    list_display = ['product', 'page_number']
    list_filter = ['product']


@admin.register(RecentRead)
class RecentReadAdmin(admin.ModelAdmin):
    list_display = ['customer', 'digital_book', 'chapter', 'last_read_at']
    list_filter = ['digital_book__category', 'last_read_at']
    search_fields = ['customer__user__username', 'digital_book__title']


@admin.register(Genre)
class GenreAdmin(admin.ModelAdmin):
    list_display = ['name', 'slug']
    search_fields = ['name', 'slug']


@admin.register(ProductReview)
class ProductReviewAdmin(admin.ModelAdmin):
    list_display = ['product', 'customer', 'rating', 'created_at']
    list_filter = ['rating', 'created_at']
    search_fields = ['product__title', 'customer__user__username']

