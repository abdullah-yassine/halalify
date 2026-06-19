from django.urls import path

from accounts.views import AppleAuthView, ScanCreateView, ScanHistoryView

urlpatterns = [
    path("auth/apple/", AppleAuthView.as_view(), name="auth-apple"),
    path("scans/", ScanCreateView.as_view(), name="scan-create"),
    path("scans/history/", ScanHistoryView.as_view(), name="scan-history"),
]
