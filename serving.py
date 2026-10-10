"""Production WSGI serving with bounded requests and an explicit proxy boundary."""
import io
import time
from email.message import Message
from http import HTTPStatus
from pathlib import Path
from types import MethodType

from server import Handler, HRStore


class WSGIHandler(Handler):
    def __init__(self,environ,store):
        self.server=store
        self.command=environ['REQUEST_METHOD']
        self.path=environ.get('PATH_INFO','/')+('?' + environ['QUERY_STRING'] if environ.get('QUERY_STRING') else '')
        self.headers=Message()
        for key,value in environ.items():
            if key.startswith('HTTP_'):
                self.headers[key[5:].replace('_','-')]=value
        self.headers['Content-Length']=environ.get('CONTENT_LENGTH','0')
        self.headers['Content-Type']=environ.get('CONTENT_TYPE','')
        self.rfile=environ['wsgi.input']
        self.wfile=io.BytesIO()
        self.client_address=(environ.get('REMOTE_ADDR','127.0.0.1'),0)
        self.response_status=500
        self.response_headers=[]

    def send_response(self,status,message=None):
        self.response_status=status

    def send_header(self,name,value):
        self.response_headers.append((name,value))

    def end_headers(self):
        pass


def create_application(store):
    def application(environ,start_response):
        request=WSGIHandler(environ,store)
        if store.public_origin and environ.get('wsgi.url_scheme')!='https':
            request.respond(403,{'error':'Remote access requires HTTPS through the configured proxy.'})
        elif request.command not in ('GET','POST','PATCH'):
            request.respond(405,{'error':'This request method is not supported.'})
        else:
            request.dispatch()
        start_response(f'{request.response_status} {HTTPStatus(request.response_status).phrase}',request.response_headers)
        return [request.wfile.getvalue()]
    return application


def create_hardened_server(store,host='127.0.0.1',port=8000,request_deadline=5,pending_limit=48,peer_pending_limit=16,**options):
    """Bound incomplete requests before WSGI/authentication can run.

    Waitress 3's channel seam is pinned and exercised with real socket tests.
    The pending budget reserves capacity for fully assembled requests.
    """
    from waitress import create_server
    from waitress.channel import HTTPChannel
    defaults={'host':host,'port':port,'threads':8,'connection_limit':100,'max_request_body_size':16384,'max_request_header_size':16384,'channel_timeout':10,'cleanup_interval':0.2,'asyncore_loop_timeout':0.1,'expose_tracebacks':False,'ident':'OpenPeople'}
    if store.public_origin:
        defaults.update(trusted_proxy='127.0.0.1',trusted_proxy_headers={'x-forwarded-proto','x-forwarded-for'},trusted_proxy_count=1,clear_untrusted_proxy_headers=True)
    defaults.update(options)
    worker_count = int(defaults['threads'])
    if worker_count < 2:
        raise ValueError('At least two HTTP workers are required to reserve non-SSO capacity.')
    import threading
    store.sso_slots = threading.BoundedSemaphore(min(2, worker_count - 1))
    server=create_server(create_application(store),**defaults)
    class BoundedChannel(HTTPChannel):
        def __init__(self,server,sock,addr,adj,map=None):
            self.pending_started=time.monotonic()
            super().__init__(server,sock,addr,adj,map=map)

        def received(self,data):
            if self.pending_started is None:self.pending_started=time.monotonic()
            result=super().received(data)
            if self.request is None:self.pending_started=None
            else:
                pending=[channel for channel in self.server.active_channels.values() if getattr(channel,'pending_started',None) is not None and not channel.will_close]
                peers=[channel for channel in pending if channel.addr[0]==self.addr[0]]
                # Retire the oldest unfinished input so a new, fragmented valid
                # request can complete. Never evict a fully assembled WSGI request.
                victims=peers if len(peers)>peer_pending_limit else pending if len(pending)>pending_limit else []
                if victims:
                    oldest=min(victims,key=lambda channel:channel.pending_started)
                    oldest.will_close=True
            return result
    server.channel_class=BoundedChannel
    original_maintenance=server.maintenance
    def maintenance(instance,now):
        original_maintenance(now)
        for channel in list(instance.active_channels.values()):
            started=getattr(channel,'pending_started',None)
            if started is not None and time.monotonic()-started>=request_deadline:
                channel.will_close=True
    server.maintenance=MethodType(maintenance,server)
    return server


def serve_workspace(db_path,host='127.0.0.1',port=8000,public_origin=None,production=False,product_profile=None,on_ready=None):
    from backup import start_backup_worker,recover_interrupted_job
    store=HRStore(db_path,public_origin,port,product_profile or ('core-hr' if production else 'full'))
    from operations import version
    version()  # Freeze the version actually loaded by this process.
    store.production_mode=production
    if production:
        from operations import production_boot_check
        report=production_boot_check(store)
        if not report['passed']:raise ValueError('Production launch refused: '+', '.join(key for key,value in report['checks'].items() if not value))
    server=create_hardened_server(store,host,port)
    print('OpenPeople is running at '+(public_origin or f'http://{host}:{port}'),flush=True)
    if store.bootstrap_token:
        print('First-run setup token is in the private file: '+str(Path(db_path).with_suffix('.setup-token')),flush=True)
    recover_interrupted_job(db_path,store.instance_id)
    stop,worker=start_backup_worker(db_path,store)
    try:
        if on_ready:on_ready(public_origin or f'http://{host}:{port}')
        server.run()
    finally:
        stop.set();worker.join(timeout=10)
        for thread in store.backup_threads:thread.join(timeout=10)
        server.task_dispatcher.shutdown();server.close()
