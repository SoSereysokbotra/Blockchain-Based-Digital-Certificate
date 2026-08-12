"""
Root URL configuration.

/admin/ is mounted only when ENABLE_ADMIN is truthy (NFR-1.12). Django's admin
already requires is_staff, but the admin login form is itself an attack surface
and a credential-stuffing target, so the safe default is for the route not to
exist at all on a deployment.
"""
from django.conf import settings
from django.conf.urls.static import static
from django.urls import include, path

urlpatterns = [
    path('api/', include('accounts.urls')),
    path('api/', include('certificates.urls')),
]

if settings.ENABLE_ADMIN:
    from django.contrib import admin

    admin.site.site_header = 'BCIP Administration'
    admin.site.site_title = 'BCIP'
    admin.site.index_title = 'Operational data'
    urlpatterns.append(path('admin/', admin.site.urls))

if settings.DEBUG:
    # In production the PDFs are served by the web server or object store, not
    # by Django.
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
