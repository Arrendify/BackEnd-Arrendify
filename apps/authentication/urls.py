from django.urls import path
from .views import  Login, Logout, UserToken,Register, user_unico, agente_inmobiliaria


urlpatterns = [
  
    path("login_api/", Login.as_view(), name="login_api"),
    path("logout_api/", Logout.as_view(), name="logout_api"),
    path("refresh-token/", UserToken.as_view(), name="refresh_token"),
    path("registro_api/", Register.as_view(), name="registro"),
    path("user_unico/", user_unico, name="user_unico"),
    path("agente_inmobiliaria/", agente_inmobiliaria, name="agente_inmobiliaria")
]