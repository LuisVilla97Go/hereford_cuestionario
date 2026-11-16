from django.urls import path

from . import views

urlpatterns = [
    path("acceso/", views.AccesoView.as_view(), name="acceso-api"),
    path("auth/login/", views.LoginView.as_view(), name="correo-login"),
    path("auth/registro/", views.RegistroView.as_view(), name="correo-registro"),
    path("auth/verificar-correo/", views.VerificarView.as_view(), name="correo-verificar"),
    path("auth/activar/", views.ActivarView.as_view(), name="invitacion-activar"),
    path("auth/aceptar-invitacion/", views.AceptarView.as_view(), name="invitacion-aceptar"),
    path("auth/refresh/", views.RefreshView.as_view(), name="jwt-refresh"),
    path("auth/logout/", views.LogoutView.as_view(), name="jwt-logout"),
    path("auth/me/", views.MeView.as_view(), name="perfil-propio"),
    path("auth/me/foto/", views.FotoView.as_view(), name="foto-propia"),
    path("auth/recuperar/", views.RecuperarView.as_view(), name="correo-recuperar"),
    path("auth/restablecer/", views.RestablecerView.as_view(), name="correo-restablecer"),
    path("procesos/<str:codigo>/", views.ProcesoView.as_view(), name="proceso-publico"),
    path(
        "procesos/<str:codigo>/participar/",
        views.ParticiparView.as_view(),
        name="proceso-participar",
    ),
]
