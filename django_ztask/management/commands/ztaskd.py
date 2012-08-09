from django.core.management.base import BaseCommand
#
from django_ztask.conf import settings
#
import zmq
from zmq.eventloop import ioloop
try:
    from zmq import PULL, PUSH
except:
    from zmq import UPSTREAM as PULL, PUSH
#
from optparse import make_option
import sys
import traceback

import logging
from multiprocessing import Process
import signal

class Command(BaseCommand):
    option_list = BaseCommand.option_list + (
        make_option('-f', '--logfile', action='store', dest='logfile', default=None, help='Tells ztaskd where to log information. Leaving this blank logs to stderr'),
        make_option('-l', '--loglevel', action='store', dest='loglevel', default='info', help='Tells ztaskd what level of information to log'),
        make_option('--multiprocess', action='store_true', default=False, help='Run ztaskd with multiprocess support'),
        make_option('--worker-pool-size', action='store', default=8, type='int', help='Number of workers in the subscriber worker pool'),
    )
    args = ''
    help = 'Start the ztaskd server'
    func_cache = {}
    io_loop = None

    def handle(self, *args, **options):
        self._setup_logger(options.get('logfile', None), options.get('loglevel', 'info'))

        if options["multiprocess"]:
            if options["worker_pool_size"]:
                self.worker_pool_size = options["worker_pool_size"]
            else:
                self.worker_pool_size = settings.ZTASKD_WORKER_POOL_SIZE

            handler = self._multiprocess_handler

            self.worker_pool = []

            self._kill_worker_pool()

            self._setup_multiprocess_signal_handling()
        else:
            handler = self._handler

        handler()

    def _setup_multiprocess_signal_handling(self):
        def keyboard_interrupt_handler(signum, frame):
            self.logger.info("Terminating children...")

            self._kill_worker_pool()

            sys.exit()

        signal.signal(signal.SIGINT, keyboard_interrupt_handler)

    def _setup_subprocess_signal_handling(self):
        def keyboard_interrupt_handler(signum, frame):
            self.logger.info("Child is terminating")

            self.io_loop.close(all_fds=True)

            sys.exit()

        signal.signal(signal.SIGINT, keyboard_interrupt_handler)

    def _kill_worker_pool(self):
        for p in self.worker_pool:
            p.terminate()

        self.worker_pool = []

    def _spawn_worker_pool(self):

        def multiprocess_worker(worker_id):
            self._setup_subprocess_signal_handling()

            # Note: forked processes need their own zmq contexts
            self.context = zmq.Context()

            job_receiver = self.context.socket(PULL)
            job_receiver.connect(
                settings.ZTASKD_SUBWORKER_MANAGEMENT_URL)

            job_status_report_sender = self.context.socket(PUSH)
            job_status_report_sender.connect(
                    settings.ZTASKD_SUBWORKER_STATUS_REPORT_URL)

            self.io_loop = ioloop.IOLoop.instance()

            def _queue_handler(socket, *args, **kwargs):
                job_tuple = self._pull_job_from_queue(job_receiver)

                if job_tuple:
                    result = self._exec_job(job_tuple, self.io_loop)

                    if None != result:
                        job_status_report_sender.send("DONE:{0}".format(result))
                    else:
                        job_status_report_sender.send("Failed")

            self.io_loop.add_handler(job_receiver, _queue_handler,
                self.io_loop.READ)
            self.io_loop.start()

        self.worker_pool = []

        self.job_distribution_socket = self.context.socket(PUSH)
        self.job_distribution_socket.bind(
            settings.ZTASKD_SUBWORKER_MANAGEMENT_URL)

        for i in range(self.worker_pool_size):
            p = Process(target = multiprocess_worker,
                        args = (i,))

            p.start()

            self.worker_pool.append(p)

        self.job_status_report_collector = self.context.socket(PULL)
        self.job_status_report_collector.bind(settings.ZTASKD_SUBWORKER_STATUS_REPORT_URL)


    def _multiprocess_handler(self):
        """
        """
        self.context = zmq.Context()

        self.logger.info("%sServer starting on %s." % ('Development ', settings.ZTASKD_WORKER_BIND_URL))
        self._on_load()

        self.logger.info("Spawning worker pool of size {0}".format(self.worker_pool_size))
        self._spawn_worker_pool()

        receiver = self.context.socket(PULL)
        receiver.bind(settings.ZTASKD_WORKER_BIND_URL)

        def _queue_handler(socket, *args, **kwargs):
            job = receiver.recv()

            self.job_distribution_socket.send(job)

        def _handle_job_completion_status(socket, *args, **kwargs):
            self.logger.info("Job status: {0}".format(self.job_status_report_collector.recv()))

        self.io_loop = ioloop.IOLoop.instance()
        self.io_loop.add_handler(receiver, _queue_handler, self.io_loop.READ)
        self.io_loop.add_handler(self.job_status_report_collector, _handle_job_completion_status,
                self.io_loop.READ)
        self.io_loop.start()

    def _handler(self):
        self.logger.info("%sServer starting on %s." % ('Development ', settings.ZTASKD_WORKER_BIND_URL))
        self._on_load()

        self.context = zmq.Context()

        socket = self.context.socket(PULL)

        socket.bind(settings.ZTASKD_WORKER_BIND_URL)

        self.logger.info("binding to '{0}'".format(settings.ZTASKD_WORKER_BIND_URL))

        def _queue_handler(socket, *args, **kwargs):
            self.logger.info("Pulling job")
            job_tuple = self._pull_job_from_queue(socket)

            if job_tuple:
                self._exec_job(job_tuple, self.io_loop)
                self.logger.info("Job complete")

        self.logger.info("running")
        self.io_loop = ioloop.IOLoop.instance()
        self.io_loop.add_handler(socket, _queue_handler, self.io_loop.READ)
        self.io_loop.start()

    def p(self, txt):
        print txt

    def _pull_job_from_queue(self, socket):
        """
        Pull a job from the socket and return a tuple with all
        we know about it.
        """
        try:
            function_name, args, kwargs, after = socket.recv_pyobj()
            if function_name == 'ztask_log':
                self.logger.warn('%s: %s' % (args[0], args[1]))
                return None

            return (function_name, args, kwargs, after)
        except Exception, e:
            self.logger.error('Error setting up function. Details:\n%s' % e)
            traceback.print_exc(e)

            return None

    def _exec_job(self, job_tuple, io_loop):
        """
        Execute a job.
        """
        (function_name, args, kwargs, after) = job_tuple

        try:
            return self._call_function(io_loop,
                function_name=function_name, args=args, kwargs=kwargs)
        except Exception, e:
            self.logger.error('Error setting up function. Details:\n%s' % e)
            traceback.print_exc(e)

            return None

    def _call_function(self, io_loop, function_name, args=None, kwargs=None):
        function_result = None

        try:
            try:
                function = self.func_cache[function_name]
            except KeyError:
                parts = function_name.split('.')
                module_name = '.'.join(parts[:-1])
                member_name = parts[-1]
                if not module_name in sys.modules:
                    __import__(module_name)
                function = getattr(sys.modules[module_name], member_name)
                self.func_cache[function_name] = function
            function_result = function(*args, **kwargs)
        except Exception, e:
            traceback.print_exc(e)

        return function_result

    def _setup_logger(self, logfile, loglevel):
        LEVELS = {
            'debug': logging.DEBUG,
            'info': logging.INFO,
            'warning': logging.WARNING,
            'error': logging.ERROR,
            'critical': logging.CRITICAL
        }

        self.logger = logging.getLogger('ztaskd')
        self.logger.setLevel(LEVELS[loglevel.lower()])
        if logfile:
            handler = logging.FileHandler(logfile, delay=True)
        else:
            handler = logging.StreamHandler()

        formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
        handler.setFormatter(formatter)
        self.logger.addHandler(handler)

    def _on_load(self):
        for callable_name in settings.ZTASKD_ON_LOAD:
            self.logger.info("ON_LOAD calling %s" % callable_name)
            parts = callable_name.split('.')
            module_name = '.'.join(parts[:-1])
            member_name = parts[-1]
            if not module_name in sys.modules:
                __import__(module_name)
            callable_fn = getattr(sys.modules[module_name], member_name)
            callable_fn()
