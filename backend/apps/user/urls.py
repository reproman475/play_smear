from django.urls import re_path, include


urlpatterns = [
    re_path(r'^v1/', include('apps.user.v1_urls')),
]
