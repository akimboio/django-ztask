from django.conf import settings

ZTASKD_WORKER_PORT = getattr(settings, 'ZTASKD_WORKER_PORT', 5555)
ZTASKD_ALWAYS_EAGER = getattr(settings, 'ZTASKD_ALWAYS_EAGER', False)
ZTASKD_DISABLED = getattr(settings, 'ZTASKD_DISABLED', False)
ZTASKD_ON_LOAD = getattr(settings, 'ZTASKD_ON_LOAD', ())

# URL for job workers; they listen and do
ZTASKD_WORKER_URL_LIST = getattr(settings, 'ZTASKD_WORKER_URL_LIST', [])

ZTASKD_WORKER_BIND_URL = getattr(settings, 'ZTASKD_WORKER_BIND_URL',
    'tcp://0.0.0.0:{0}'.format(ZTASKD_WORKER_PORT))

# URL used by job workers for dispatching
# jobs to subworkers
ZTASKD_SUBWORKER_MANAGEMENT_URL = getattr(
    settings,
    'ZTASKD_SUBWORKER_MANAGEMENT_URL',
    'tcp://127.0.0.1:5556')

# URL used by subworkers for sending job
# status updates to the parent worker
ZTASKD_SUBWORKER_STATUS_REPORT_URL = getattr(
    settings,
    'ZTASKD_SUBWORKER_STATUS_REPORT_URL',
    'tcp://127.0.0.1:5557')

ZTASKD_SUBWORKER_WORKER_START_PORT = getattr(
    settings,
    'ZTASKD_SUBWORKER_WORKER_START_PORT',
    5560)
