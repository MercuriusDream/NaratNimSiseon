import logging
from functools import wraps
from rest_framework.response import Response
from rest_framework import status
from django.http import Http404

logger = logging.getLogger(__name__)

def api_action_wrapper(default_error_message="오류가 발생했습니다.", log_prefix="Error"):
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            # self is args[0] (the viewset instance)
            # request is args[1]
            # pk (or other path params) are in kwargs
            viewset_instance = args[0]
            action_name = func.__name__
            # Construct a more specific log prefix if possible, e.g., using pk
            item_pk = kwargs.get('pk', 'N/A')
            full_log_prefix = f"{log_prefix} in {viewset_instance.__class__.__name__}.{action_name} (pk={item_pk})"

            try:
                return func(*args, **kwargs)
            except Http404 as e:
                logger.warning(f"{full_log_prefix}: Resource not found - {e}")
                return Response({
                    'status': 'error',
                    'message': str(e) if str(e) else "리소스를 찾을 수 없습니다." # Provide a default if str(e) is empty
                }, status=status.HTTP_404_NOT_FOUND)
            except Exception as e:
                logger.error(f"{full_log_prefix}: {e}")
                return Response({
                    'status': 'error',
                    'message': default_error_message
                }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
        return wrapper
    return decorator
