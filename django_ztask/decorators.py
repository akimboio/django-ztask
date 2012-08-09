from functools import wraps
from django.conf import settings

import logging

def task():
    def build_job_distribution_socket():
        """
        Set up a push connection to all of the worker nodes
        so we can send jobs.
        """
        from django_ztask.context import shared_context as context
        socket = context.socket(PUSH)
        for worker_url in settings.ZTASKD_WORKER_URL_LIST:
            socket.connect(worker_url)

        return socket
    try:
        from zmq import PUSH
    except:
        from zmq import DOWNSTREAM as PUSH
    def wrapper(func):
        function_name = '%s.%s' % (func.__module__, func.__name__)
        
        logger = logging.getLogger('ztaskd')
        logger.info('Registered task: %s' % function_name)
        
        socket = build_job_distribution_socket()

        @wraps(func)
        def _func(*args, **kwargs):
            after = kwargs.pop('__ztask_after', 0)
            if settings.ZTASKD_DISABLED:
                try:
                    socket.send_pyobj(('ztask_log', ('Would have called but ZTASKD_DISABLED is True', function_name), None, 0))
                except:
                    logger.info('Would have sent %s but ZTASKD_DISABLED is True' % function_name)
                return
            elif settings.ZTASKD_ALWAYS_EAGER:
                logger.info('Running %s in ZTASKD_ALWAYS_EAGER mode' % function_name)
                if after > 0:
                    logger.info('Ignoring timeout of %d seconds because ZTASKD_ALWAYS_EAGER is set' % after)
                func(*args, **kwargs)
            else:
                try:
                    socket.send_pyobj((function_name, args, kwargs, after))
                except Exception, e:
                    if after > 0:
                        logger.info('Ignoring timeout of %s seconds because function is being run in-process' % after)
                    func(*args, **kwargs)

        setattr(func, 'async', _func)

        return func
    
    return wrapper
