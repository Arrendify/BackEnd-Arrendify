from django.urls import path
from .views import  Login, Logout, UserToken, Register, ChangePasswordView, UserInfoView, user_unico, agente_inmobiliaria
from .views_password_recovery import RecuperarPasswordView, ResetPasswordView

urlpatterns = [
  
    path("login_api/", Login.as_view(), name="login_api"),
    path("logout_api/", Logout.as_view(), name="logout_api"),
    path("refresh-token/", UserToken.as_view(), name="refresh_token"),
    path("registro_api/", Register.as_view(), name="registro"),
    path("user_unico/", user_unico, name="user_unico"),
    path("agente_inmobiliaria/", agente_inmobiliaria, name="agente_inmobiliaria"),
    path("change_password/", ChangePasswordView.as_view(), name='change_password'),
    path("user_info/",UserInfoView.as_view(), name='user_info'),
    path("RecuperarPassword/recupera_password/", RecuperarPasswordView.as_view(), name='recupera_password'),
    path("RecuperarPassword/reset_password/", ResetPasswordView.as_view(), name='reset_password'),
]