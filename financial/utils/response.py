from django.http import HttpResponse


def get_file_response(filename: str, content: str):
    response = HttpResponse(content_type='text/csv charset=utf-8')
    response['Content-Disposition'] = 'attachment; filename={}'.format(filename)
    response.write(content)
    return response
