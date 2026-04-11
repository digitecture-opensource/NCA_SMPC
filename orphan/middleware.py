from django.shortcuts import redirect
from django.urls import reverse


class LoginRequiredMiddleware:
    """
    Middleware that requires login for all views except login/logout.
    Redirects unauthenticated users to the login page.
    """

    def __init__(self, get_response):
        self.get_response = get_response
        # Paths that don't require authentication
        self.public_paths = ['/login/', '/logout/', '/static/', '/media/']

    def __call__(self, request):
        # Check if path is public
        is_public = any(request.path.startswith(path) for path in self.public_paths)

        # If not public and user is not authenticated, redirect to login
        if not is_public and not request.user.is_authenticated:
            return redirect(f"{reverse('orphan:login')}?next={request.path}")

        response = self.get_response(request)
        return response
