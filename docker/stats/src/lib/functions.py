import time
import socket



def timeit(method):
    def test_time_exec(*args,**kwargs):
        start_time = time.time()
        out = method(*args,**kwargs)
        time_elapsed = time.time() - start_time
        method_name = method.__name__
        print(f"--- execution time of method {method_name}: {time_elapsed:.3f} seconds ---")
        return out
    return test_time_exec

def getHost(ip):
    """
    This method returns the 'True Host' name for a
    given IP address
    """
    try:
        data = socket.gethostbyaddr(ip)
        host = repr(data[0])
        return host
    except Exception:
        # fail gracefully
        return False