from django.urls import path

from products.views import ProductLookupView

urlpatterns = [
    path("products/<str:barcode>/", ProductLookupView.as_view(), name="product-lookup"),
]
