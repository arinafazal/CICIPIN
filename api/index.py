from app import app
from werkzeug.wrappers import Request
import io

def handler(event, context):
    # Simple WSGI adapter for Vercel
    method = event['httpMethod']
    path = event['path']
    query = event.get('queryStringParameters', {}) or {}
    headers = event.get('headers', {})
    body = event.get('body', '')

    # Build environ
    environ = {
        'REQUEST_METHOD': method,
        'PATH_INFO': path,
        'QUERY_STRING': '&'.join([f"{k}={v}" for k, v in query.items()]),
        'CONTENT_TYPE': headers.get('content-type', ''),
        'CONTENT_LENGTH': str(len(body) if body else 0),
        'SERVER_NAME': 'vercel',
        'SERVER_PORT': '443',
        'wsgi.version': (1, 0),
        'wsgi.url_scheme': 'https',
        'wsgi.input': io.BytesIO(body.encode('utf-8') if body else b''),
        'wsgi.errors': io.StringIO(),
        'wsgi.multithread': False,
        'wsgi.multiprocess': False,
        'wsgi.run_once': False,
    }

    # Add HTTP headers
    for k, v in headers.items():
        environ[f'HTTP_{k.upper().replace("-", "_")}'] = v

    # Response collector
    response_data = {'status': None, 'headers': [], 'body': []}

    def start_response(status, response_headers, exc_info=None):
        response_data['status'] = status
        response_data['headers'] = response_headers

    # Call Flask app
    result = app.wsgi_app(environ, start_response)
    response_data['body'] = [chunk for chunk in result]

    # Return Vercel response
    status_code = int(response_data['status'].split()[0])
    headers_dict = {k: v for k, v in response_data['headers']}
    body_str = b''.join(response_data['body']).decode('utf-8')

    return {
        'statusCode': status_code,
        'headers': headers_dict,
        'body': body_str
    }