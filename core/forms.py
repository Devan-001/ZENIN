from django import forms
from django.contrib.auth.forms import UserCreationForm
import re
from .models import User, SellerProfile, Product, DigitalBook, Chapter, ChapterPage, ProductReview, CustomerFeedback


EMAIL_PATTERN = re.compile(r'^[a-z][a-z0-9._%+-]*@[a-z0-9.-]+\.[a-z]{2,}$')
PHONE_PATTERN = re.compile(r'^\d{10}$')


class MultiFileInput(forms.ClearableFileInput):
    allow_multiple_selected = True


class MultiFileField(forms.FileField):
    widget = MultiFileInput

    def clean(self, data, initial=None):
        single_file_clean = super().clean
        if data is None:
            return []
        if not isinstance(data, (list, tuple)):
            data = [data]
        return [single_file_clean(d, initial) for d in data]


# ─────────────────────────────────────────
# Registration Forms
# ─────────────────────────────────────────
class CustomerRegistrationForm(UserCreationForm):
    email = forms.EmailField(required=True)
    phone_number = forms.CharField(max_length=10, required=True)
    first_name = forms.CharField(max_length=50, required=True)
    last_name = forms.CharField(max_length=50, required=True)

    class Meta:
        model = User
        fields = ['username', 'first_name', 'last_name', 'email', 'phone_number', 'password1', 'password2']

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['email'].widget.attrs.update({'placeholder': 'name@example.com'})
        self.fields['phone_number'].widget.attrs.update({'maxlength': '10', 'inputmode': 'numeric', 'placeholder': '10-digit phone number'})

    def clean_email(self):
        email = (self.cleaned_data.get('email') or '').strip()
        if not EMAIL_PATTERN.match(email):
            raise forms.ValidationError("Enter a valid email in standard format. Email must start with a lowercase letter.")
        normalized_email = email.lower()
        if User.objects.filter(email__iexact=normalized_email).exists():
            raise forms.ValidationError("An account with this email already exists.")
        return normalized_email

    def clean_phone_number(self):
        phone_number = (self.cleaned_data.get('phone_number') or '').strip()
        if not PHONE_PATTERN.match(phone_number):
            raise forms.ValidationError("Phone number must contain exactly 10 digits.")
        return phone_number

    def save(self, commit=True):
        user = super().save(commit=False)
        user.email = self.cleaned_data['email']
        user.is_customer = True
        if commit:
            user.save()
            from .models import CustomerProfile
            CustomerProfile.objects.create(user=user, phone_number=self.cleaned_data['phone_number'])
        return user


class SellerRegistrationForm(UserCreationForm):
    email = forms.EmailField(required=True)
    phone_number = forms.CharField(max_length=10, required=True)
    first_name = forms.CharField(max_length=50, required=True)
    last_name = forms.CharField(max_length=50, required=True)
    shop_name = forms.CharField(max_length=200, required=True,
                                help_text="Your store/shop name visible to buyers.")
    seller_license = forms.FileField(
        required=True,
        help_text="Upload your selling license (PDF/JPG/PNG).",
        widget=forms.ClearableFileInput(attrs={'accept': '.pdf,.jpg,.jpeg,.png,application/pdf,image/*'}),
    )

    class Meta:
        model = User
        fields = [
            'username', 'first_name', 'last_name', 'email', 'phone_number',
            'password1', 'password2', 'shop_name', 'seller_license'
        ]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['email'].widget.attrs.update({'placeholder': 'name@example.com'})
        self.fields['phone_number'].widget.attrs.update({'maxlength': '10', 'inputmode': 'numeric', 'placeholder': '10-digit phone number'})

    def clean_email(self):
        email = (self.cleaned_data.get('email') or '').strip()
        if not EMAIL_PATTERN.match(email):
            raise forms.ValidationError("Enter a valid email in standard format. Email must start with a lowercase letter.")
        normalized_email = email.lower()
        if User.objects.filter(email__iexact=normalized_email).exists():
            raise forms.ValidationError("An account with this email already exists.")
        return normalized_email

    def clean_phone_number(self):
        phone_number = (self.cleaned_data.get('phone_number') or '').strip()
        if not PHONE_PATTERN.match(phone_number):
            raise forms.ValidationError("Phone number must contain exactly 10 digits.")
        return phone_number

    def clean_seller_license(self):
        seller_license = self.cleaned_data.get('seller_license')
        if not seller_license:
            raise forms.ValidationError("Please upload your seller license.")

        name = seller_license.name.lower()
        if not name.endswith(('.pdf', '.jpg', '.jpeg', '.png')):
            raise forms.ValidationError("License must be a PDF, JPG, or PNG file.")
        return seller_license

    def save(self, commit=True):
        user = super().save(commit=False)
        user.email = self.cleaned_data['email']
        user.is_seller = True
        if commit:
            user.save()
            SellerProfile.objects.create(
                user=user,
                shop_name=self.cleaned_data['shop_name'],
                phone_number=self.cleaned_data['phone_number'],
                seller_license=self.cleaned_data['seller_license'],
                approved=False
            )
        return user


# ─────────────────────────────────────────
# Product Form (Seller)
# ─────────────────────────────────────────
class ProductForm(forms.ModelForm):
    class Meta:
        model = Product
        fields = ['title', 'category', 'genres', 'description', 'price', 'stock', 'cover_image']
        widgets = {
            'description': forms.Textarea(attrs={'rows': 4}),
            'genres': forms.SelectMultiple(attrs={'size': 6}),
        }

    def clean_price(self):
        price = self.cleaned_data.get('price')
        if price is not None and price <= 0:
            raise forms.ValidationError("Price must be a positive value.")
        return price

    def clean_stock(self):
        stock = self.cleaned_data.get('stock')
        if stock is not None and stock < 0:
            raise forms.ValidationError("Stock cannot be negative.")
        return stock


class MultiProductPreviewUploadForm(forms.Form):
    preview_images = MultiFileField(
        required=False,
        widget=MultiFileInput(attrs={'accept': 'image/*', 'multiple': True}),
        label='Preview Pages',
        help_text='Optional: select multiple page images to show buyers before purchase.'
    )


# ─────────────────────────────────────────
# Digital Book & Chapter Forms (Admin)
# ─────────────────────────────────────────
class DigitalBookForm(forms.ModelForm):
    class Meta:
        model = DigitalBook
        fields = ['title', 'category', 'genres', 'description', 'cover_image']
        widgets = {
            'description': forms.Textarea(attrs={'rows': 4}),
            'genres': forms.SelectMultiple(attrs={'size': 6}),
        }


class ChapterForm(forms.ModelForm):
    class Meta:
        model = Chapter
        fields = ['number', 'title']

    def clean_number(self):
        number = self.cleaned_data.get('number')
        if number is not None and number < 1:
            raise forms.ValidationError("Chapter number must be at least 1.")
        return number


class ChapterPageForm(forms.ModelForm):
    class Meta:
        model = ChapterPage
        fields = ['page_number', 'image']


class MultiPageUploadForm(forms.Form):
    """Upload chapter content as either page images or a single PDF/CBZ file."""
    images = forms.FileField(
        required=False,
        widget=MultiFileInput(attrs={'accept': 'image/*'}),
        label='Chapter Pages (optional, select multiple images)',
        help_text='Use this for image-based chapters. Select images in page order.'
    )
    chapter_file = forms.FileField(
        required=False,
        widget=forms.ClearableFileInput(attrs={'accept': '.pdf,.cbz,application/pdf,application/x-cbz,application/zip'}),
        label='Chapter File (optional: .pdf or .cbz)',
        help_text='Upload one PDF or CBZ file as an alternative to image pages.'
    )

    def clean_chapter_file(self):
        chapter_file = self.cleaned_data.get('chapter_file')
        if not chapter_file:
            return chapter_file

        ext = chapter_file.name.rsplit('.', 1)[-1].lower() if '.' in chapter_file.name else ''
        if ext not in {'pdf', 'cbz'}:
            raise forms.ValidationError('Only .pdf and .cbz files are supported.')
        return chapter_file


class BulkChapterUploadForm(forms.Form):
    chapter_files = MultiFileField(
        required=True,
        widget=MultiFileInput(attrs={'accept': '.pdf,.cbz,application/pdf,application/x-cbz,application/zip', 'multiple': True}),
        label='Chapter Files',
        help_text='Upload up to 100 chapter files (.pdf/.cbz). Filenames with numbers are used as chapter numbers.'
    )

    def clean(self):
        cleaned_data = super().clean()
        files = cleaned_data.get('chapter_files') or []

        if not files:
            raise forms.ValidationError('Please select at least one chapter file.')

        if len(files) > 100:
            raise forms.ValidationError('You can upload at most 100 chapters at once.')

        invalid = []
        for f in files:
            ext = f.name.rsplit('.', 1)[-1].lower() if '.' in f.name else ''
            if ext not in {'pdf', 'cbz'}:
                invalid.append(f.name)

        if invalid:
            raise forms.ValidationError(
                f"Unsupported files: {', '.join(invalid)}. Only .pdf and .cbz are allowed."
            )

        return cleaned_data


# ─────────────────────────────────────────
# Checkout Form
# ─────────────────────────────────────────
class CheckoutForm(forms.Form):
    shipping_address = forms.CharField(
        widget=forms.Textarea(attrs={'rows': 3, 'placeholder': 'Full shipping address…'}),
        required=True
    )


class ProductReviewForm(forms.ModelForm):
    class Meta:
        model = ProductReview
        fields = ['rating', 'comment']
        widgets = {
            'rating': forms.Select(choices=[(i, f"{i} / 5") for i in range(1, 6)]),
            'comment': forms.Textarea(attrs={'rows': 3, 'placeholder': 'Write your review (optional)'}),
        }


class CustomerFeedbackForm(forms.ModelForm):
    class Meta:
        model = CustomerFeedback
        fields = ['feedback_type', 'subject', 'message']
        widgets = {
            'feedback_type': forms.Select(),
            'subject': forms.TextInput(attrs={'placeholder': 'Short title for your message'}),
            'message': forms.Textarea(attrs={'rows': 5, 'placeholder': 'Write your feedback or complaint...'}),
        }
