from django.urls import path
from . import views

app_name = "orphan"

urlpatterns = [
    path("", views.home, name="home"),
    path("orphan/", views.page1_list, name="list"),
    path("orphan/detail/<int:orphan_id>/", views.page2_detail, name="detail"),
    path("smpc/", views.smpc_list, name="smpc_list"),
    path("smpc/<int:smpc_id>/", views.smpc_detail, name="smpc_detail"),
    path("smpc/<int:smpc_id1>/compare/<int:smpc_id2>/", views.smpc_compare, name="smpc_compare"),
    path("api/smpc-list/", views.api_smpc_list, name="api_smpc_list"),
    path("login/", views.login_view, name="login"),
    path("logout/", views.logout_view, name="logout"),
    path("od/apply/", views.od_apply, name="od_apply"),
    path("idmp/product-master/", views.idmp_product_master, name="idmp_product_master"),
]