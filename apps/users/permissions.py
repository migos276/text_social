from rest_framework import permissions


class IsOwnerOrReadOnly(permissions.BasePermission):
    """
    Custom permission to only allow owners of an object to edit it.
    """
    
    def has_object_permission(self, request, view, obj):
        # Read permissions are allowed to any request
        if request.method in permissions.SAFE_METHODS:
            return True
        
        # Write permissions are only allowed to the owner.
        if obj == request.user:
            return True

        owner = getattr(obj, 'author', None) or getattr(obj, 'user', None)
        return owner == request.user


class IsAuthenticatedOrReadOnly(permissions.BasePermission):
    """
    Allow any access to safe methods, but only allow authenticated users
    to modify resources.
    """
    
    def has_permission(self, request, view):
        if request.method in permissions.SAFE_METHODS:
            return True
        return request.user and request.user.is_authenticated
