from django.urls import path
from . import views

urlpatterns = [
    # ── Public ──────────────────────────────────────
    path('', views.home, name='home'),
    path('browse/', views.product_catalog, name='product_catalog'),
    path('browse/<int:pk>/', views.product_detail, name='product_detail'),
    path('browse/<int:pk>/review/', views.add_product_review, name='add_product_review'),
    path('digital/', views.digital_catalog, name='digital_catalog'),
    path('digital/book/<int:pk>/', views.digital_book_detail, name='digital_book_detail'),
    path('digital/book/<int:book_pk>/chapter/<int:num>/', views.read_chapter, name='read_chapter'),
    path('digital/book/<int:book_pk>/chapter/<int:num>/download/pdf/', views.download_chapter_pdf, name='download_chapter_pdf'),

    # ── Auth ────────────────────────────────────────
    path('register/', views.register_choice, name='register'),
    path('register/customer/', views.register_customer, name='register_customer'),
    path('register/seller/', views.register_seller, name='register_seller'),
    path('login/', views.login_view, name='login'),
    path('logout/', views.logout_view, name='logout'),

    # ── Customer ────────────────────────────────────
    path('cart/', views.cart_view, name='cart'),
    path('cart/add/<int:pk>/', views.add_to_cart, name='add_to_cart'),
    path('cart/remove/<int:pk>/', views.remove_from_cart, name='remove_from_cart'),
    path('cart/update/<int:pk>/', views.update_cart, name='update_cart'),
    path('checkout/', views.checkout, name='checkout'),
    path('orders/', views.order_history, name='order_history'),
    path('orders/<int:pk>/bill/', views.order_bill, name='order_bill'),
    path('orders/<int:pk>/bill/pdf/', views.order_bill_pdf, name='order_bill_pdf'),
    path('support/feedback/', views.customer_feedback, name='customer_feedback'),

    # ── Seller ──────────────────────────────────────
    path('seller/', views.seller_dashboard, name='seller_dashboard'),
    path('seller/products/', views.seller_products, name='seller_products'),
    path('seller/products/add/', views.product_create, name='product_add'),
    path('seller/products/<int:pk>/edit/', views.product_edit, name='product_edit'),
    path('seller/products/<int:pk>/delete/', views.product_delete, name='product_delete'),
    path('seller/orders/', views.seller_orders, name='seller_orders'),
    path('seller/orders/<int:pk>/update/', views.seller_order_update, name='seller_order_update'),
    path('seller/orders/<int:pk>/invoice/pdf/', views.seller_order_bill_pdf, name='seller_order_bill_pdf'),

    # ── Admin panel ─────────────────────────────────
    path('panel/sellers/', views.admin_seller_requests, name='admin_seller_requests'),
    path('panel/sellers/manage/', views.admin_manage_sellers, name='admin_manage_sellers'),
    path('panel/sellers/<int:pk>/toggle-status/', views.toggle_seller_status, name='toggle_seller_status'),
    path('panel/sellers/<int:pk>/approve/', views.approve_seller, name='approve_seller'),
    path('panel/sellers/<int:pk>/reject/', views.reject_seller, name='reject_seller'),
    path('panel/customers/', views.admin_manage_customers, name='admin_manage_customers'),
    path('panel/customers/<int:pk>/toggle-status/', views.toggle_customer_status, name='toggle_customer_status'),
    path('panel/customers/<int:pk>/orders/', views.customer_purchase_history, name='customer_purchase_history'),
    path('panel/reports/dashboard/', views.admin_reporting_dashboard, name='admin_reporting_dashboard'),
    path('panel/reports/', views.monthly_report, name='monthly_report'),
    path('panel/reports/<int:year>/<int:month>/download/', views.download_monthly_sales, name='download_monthly_sales'),
    path('panel/feedback/', views.admin_customer_feedbacks, name='admin_customer_feedbacks'),
    path('panel/feedback/<int:pk>/reply/', views.admin_feedback_reply, name='admin_feedback_reply'),
    path('panel/feedback/<int:pk>/update/', views.admin_update_feedback_status, name='admin_update_feedback_status'),
    path('panel/digital/', views.admin_digital_books, name='admin_digital_books'),
    path('panel/digital/add/', views.digital_book_create, name='digital_book_create'),
    path('panel/digital/<int:pk>/edit/', views.digital_book_edit, name='digital_book_edit'),
    path('panel/digital/<int:pk>/delete/', views.digital_book_delete, name='digital_book_delete'),
    path('panel/digital/<int:book_pk>/chapters/', views.chapter_list, name='chapter_list'),
    path('panel/digital/<int:book_pk>/chapters/add/', views.chapter_create, name='chapter_create'),
    path('panel/digital/<int:book_pk>/chapters/bulk-add/', views.chapter_bulk_upload, name='chapter_bulk_upload'),
    path('panel/digital/<int:book_pk>/chapters/<int:num>/delete/', views.chapter_delete, name='chapter_delete'),
]
