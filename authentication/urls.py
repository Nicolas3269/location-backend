from django.urls import path
from rest_framework_simplejwt.views import (
    TokenVerifyView,
)

from authentication.views import (
    get_user_profile,
    get_user_profile_detailed,
    google_redirect_callback,
    login_with_google,
    logout_view,
    refresh_token_view,
    request_otp_login,
    verify_otp_login,
)

app_name = "authentication"

urlpatterns = [
    # Routes pour l'authentification
    path("google/", login_with_google, name="login_with_google"),
    path("google/callback/", google_redirect_callback, name="google_redirect_callback"),
    path("profile/", get_user_profile, name="get_user_profile"),
    path(
        "profile/detailed/", get_user_profile_detailed, name="get_user_profile_detailed"
    ),
    path("otp/request/", request_otp_login, name="request_otp_login"),
    path("otp/verify/", verify_otp_login, name="verify_otp_login"),
    path("logout/", logout_view, name="logout"),
    # Routes pour les tokens JWT
    path("token/refresh/", refresh_token_view, name="token_refresh"),
    path("token/verify/", TokenVerifyView.as_view(), name="token_verify"),
]
