from django.urls import path

from . import views

app_name = "notifications"

urlpatterns = [
    path("request/", views.create_notification_request, name="create_request"),
    path("requests/", views.list_notification_requests, name="list_requests"),
    path("mark-sent/", views.mark_notifications_sent, name="mark_sent"),
]
