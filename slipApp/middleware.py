import time
import logging

logger = logging.getLogger("requestlog")

class RequestLogMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response
    def __call__(self, request):
        start = time.time()
        response = self.get_response(request)
        duration = int((time.time() - start) * 1000)
        user = getattr(request, "user", None)
        uid = getattr(user, "id", None)
        logger.info(f"{request.method} {request.path} {response.status_code} uid={uid} {duration}ms")
        return response
