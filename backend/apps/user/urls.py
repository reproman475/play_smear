from django.urls import include, re_path

urlpatterns = [
    re_path(r"^v1/", include("apps.user.v1_urls")),
]
