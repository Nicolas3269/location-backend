from django.urls import path
from . import views

app_name = 'quittance'

urlpatterns = [
    path('generate/', views.generate_quittance_pdf, name='generate'),
]
