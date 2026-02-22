from django.urls import path
from . import views

app_name = "orphan"

urlpatterns = [
    path("", views.page1_list, name="list"),
    path("detail/<int:orphan_id>/", views.page2_detail, name="detail"),
    path("detail/<int:orphan_id>/submit/", views.submit_item, name="submit"),
    path("detail/<int:orphan_id>/approve/", views.approve_item, name="approve"),
    path("detail/<int:orphan_id>/return/", views.return_item, name="return"),
]