import logging

logger = logging.getLogger(__name__)


def get_hijacker_id(request):
    hijack_history = request.session.get('hijack_history')

    if hijack_history and isinstance(hijack_history, list):
        try:
            hijacker_id = int(hijack_history[0])
            return hijacker_id
        except ValueError as e:
            logger.info(e)
