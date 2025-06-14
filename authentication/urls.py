from django.urls import path
from rest_framework_simplejwt.views import (
    TokenVerifyView,
)

from authentication.views import (
    login_with_google,
    refresh_token_view,
    request_otp_login,
    verify_otp_login,
)

app_name = "authentication"

urlpatterns = [
    # Routes pour l'authentification
    path("google/", login_with_google, name="login_with_google"),
    path("otp/request/", request_otp_login, name="request_otp_login"),
    path("otp/verify/", verify_otp_login, name="verify_otp_login"),
    # Routes pour les tokens JWT
    path("token/refresh/", refresh_token_view, name="token_refresh"),
    path("token/verify/", TokenVerifyView.as_view(), name="token_verify"),
]
