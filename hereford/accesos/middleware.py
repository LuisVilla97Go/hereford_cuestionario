from django.utils.cache import add_never_cache_headers
from django.utils.deprecation import MiddlewareMixin


class ApiNoStoreMiddleware(MiddlewareMixin):
    def process_response(self, request, response):
        if request.path_info.startswith("/api/") or request.path_info == "/acceso":
            add_never_cache_headers(response)
        return response
