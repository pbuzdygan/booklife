"""Small response hardening that does not require a third-party dependency."""


class SecurityHeadersMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)
        response.setdefault(
            "Content-Security-Policy",
            "; ".join(
                [
                    "default-src 'self'",
                    "base-uri 'none'",
                    "connect-src 'self'",
                    "font-src 'self'",
                    "form-action 'self'",
                    "frame-ancestors 'none'",
                    "img-src 'self' data:",
                    "object-src 'none'",
                    "script-src 'self'",
                    "style-src 'self'",
                    "worker-src 'self'",
                ]
            ),
        )
        response.setdefault("Permissions-Policy", "camera=(self), geolocation=(), microphone=()")
        if request.is_secure():
            response.setdefault("Cross-Origin-Opener-Policy", "same-origin")
        response.setdefault("Cache-Control", "private, no-store")
        return response
