from django.urls import path
from . import views

app_name = "orphan"

urlpatterns = [
    path("", views.page1_list, name="list"),
    path("detail/<int:orphan_id>/", views.page2_detail, name="detail"),
]