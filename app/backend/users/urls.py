from django.urls import path
from .views import RegisterView, MeView, CambiarEmailView, ChangePasswordView, ProfilePhotoView

urlpatterns = [
    path('register/', RegisterView.as_view(), name='register'),
    path('me/', MeView.as_view(), name='me'),
    path('me/foto/', ProfilePhotoView.as_view(), name='profile-photo'),
    path('me/cambiar-email/', CambiarEmailView.as_view(), name='cambiar-email'),
    path('me/cambiar-password/', ChangePasswordView.as_view(), name='change-password'),
]