from django.urls import path

from portals.views import ParentPortalLoginView


urlpatterns = [
    path("parent/login/", ParentPortalLoginView.as_view(), name="parent-portal-login"),
]
