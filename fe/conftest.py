import requests
import threading
from urllib.parse import urljoin
from be import serve
from be.model.store import init_completed_event
from fe import conf

thread: threading.Thread = None


# 修改这里启动后端程序，如果不需要可删除这行代码
def run_backend():
    # rewrite this if rewrite backend
    serve.be_run()


def pytest_configure(config):
    global thread
    print("frontend begin test")
    # Run backend in a daemon thread to avoid teardown hang
    thread = threading.Thread(target=run_backend, daemon=True)
    thread.start()
    init_completed_event.wait()


def pytest_unconfigure(config):
    url = urljoin(conf.URL, "shutdown")
    try:
        # Ensure we don't block indefinitely if shutdown route is unavailable
        requests.get(url, timeout=3)
    except Exception:
        pass
    # Avoid indefinite blocking; daemon thread allows process exit
    thread.join(timeout=5)
    print("frontend end test")
