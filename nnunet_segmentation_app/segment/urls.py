from django.urls import path
from . import views

urlpatterns = [
    path('', views.home, name='home'),
    path('upload/', views.upload_files, name='upload_files'),
    path('segment/', views.segment_files, name='segment_files'),
    path('submit-feedback/', views.submit_feedback, name='submit_feedback'),
    path("upload-files/", views.upload_files, name="upload_files"),
    path("segment-files/", views.segment_files, name="segment_files"),
]

