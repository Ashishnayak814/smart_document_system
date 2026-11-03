from django.urls import path
from . import views

urlpatterns = [
    path('', views.dashboard, name='dashboard'),
    path('dashboard/', views.dashboard, name='dashboard_home'),
    path('documents/', views.documents_list, name='documents'),
    path('documents/upload/', views.upload_document, name='upload_document'),
    path('categories/', views.categories, name='categories'),
    path('categories/<slug:category_slug>/', views.category_detail, name='category_detail'),
    path('search/', views.search_documents, name='search_documents'),
    path('documents/<int:doc_id>/', views.document_view, name='document_view'),
    path('documents/<int:doc_id>/download/', views.download_document, name='download_document'),
    path('documents/<int:doc_id>/delete/', views.delete_document, name='delete_document'),
    path('profile/', views.profile, name='profile'),
    path('settings/', views.settings, name='settings'),
    path('logout/', views.logout_view, name='logout'),
]
