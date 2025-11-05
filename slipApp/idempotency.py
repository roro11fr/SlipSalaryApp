import hashlib
from django.http import JsonResponse
from .models import IdempotencyKey

def idempotent(view_func):
    def _wrap(view, request, *args, **kwargs):
        key = request.headers.get("Idempotency-Key")
        if not key:
            return view_func(view, request, *args, **kwargs)
        fp_src = f"{request.user.id}|{request.path}|{request.body.decode('utf-8','ignore')}"
        fp = hashlib.sha256(fp_src.encode()).hexdigest()
        existing = IdempotencyKey.objects.filter(key=key, user=request.user, path=request.path).first()
        if existing and existing.request_fingerprint == fp and existing.response_body is not None:
            return JsonResponse(existing.response_body, status=200, safe=False)
        resp = view_func(view, request, *args, **kwargs)
        try:
            body = resp.data if hasattr(resp, "data") else None
            IdempotencyKey.objects.update_or_create(
                key=key,
                user=request.user,
                path=request.path,
                defaults={"request_fingerprint": fp, "response_body": body},
            )
        except Exception:
            pass
        return resp
    return _wrap
