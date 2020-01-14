from pathlib import Path

import imghdr
import zipfile
import rarfile

import mimetypes
from aiohttp import web
import aiohttp_cors
import aiofiles

import os

currect_dir = './'

def zip_as_html(filepath: Path, prefix, file_get) -> str:
    
    file_extension = filepath.as_posix().split('.')[-1]

    assert file_extension in ['zip', 'rar', 'cbz', 'cbr']

    index_of = "Index of /{}".format(filepath)
    h1 = "<h1>{}</h1>".format(index_of)
    index_list = []
    zf = zipfile.ZipFile(filepath)
    dir_index = [str(info.filename) for info in zf.infolist()]

    for _file in sorted(dir_index):
        # show file url as relative to static path
        file_url = prefix + '/' + str(file_get) + '/' + _file
        # if file is a directory, add '/' to the end of the name
        file_name = _file
        index_list.append(
            '<li><a href="{url}">{name}</a></li>'.format(url=file_url,
                                                         name=file_name)
        )
    ul = "<ul>\n{}\n</ul>".format('\n'.join(index_list))
    body = "<body>\n{}\n{}\n</body>".format(h1, ul)
    head_str = "<head>\n<title>{}</title>\n</head>".format(index_of)
    html = "<html>\n{}\n{}\n</html>".format(head_str, body)
    return html

async def zipmedia(request):
    file_get = request.match_info['file_get']
    if isinstance(file_get, Path):
        file_get = str(file_get)
    while file_get.startswith('/'):
        file_get = file_get[1:]
    file_get = '/' + file_get
    
    if file_get.startswith('/'):
        file_get = file_get[1:]
    filepath = Path(currect_dir).joinpath(file_get).resolve()
    file_extension = filepath.as_posix().split('.')[-1]

    if file_extension in ['zip', 'rar', 'cbz', 'cbr']:
        html_ret = zip_as_html(filepath, '/zipmedia', file_get)
        ret_resp = web.Response(text=html_ret, content_type="text/html")
    else:
        files = filepath.as_posix().split('/')
        index_zip = 0
        for infile in files:
            index_zip = index_zip + 1
            if infile.split('.')[-1] in ['zip', 'rar', 'cbz', 'cbr']:
                 break
        if index_zip < len(files):
            file_in_zip = '/'.join(files[index_zip:])
            file_zip = '/'.join(files[:index_zip])
            zf = zipfile.ZipFile(file_zip)
            data = zf.read(file_in_zip)
            ret_resp = web.Response(body=data, content_type="application/octet-stream")
        else:
            ret_resp = web.Response(text="test")
    return ret_resp

app = web.Application()

app.add_routes([web.static('/media', currect_dir, show_index=True)])

app.add_routes([web.get(r'/zipmedia/{file_get:.*}', zipmedia)])

cors = aiohttp_cors.setup(app, defaults={
    "*": aiohttp_cors.ResourceOptions(
            allow_credentials=True,
            expose_headers="*",
            allow_headers="*",
        )
})

for route in list(app.router.routes()):
    cors.add(route)

if __name__ == '__main__':
    web.run_app(app, port=60009)