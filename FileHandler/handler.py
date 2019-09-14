import zipfile
import rarfile
import io
import base64
from os.path import isfile, join
from PIL import Image
import mimetypes
from aiohttp import web
import aiohttp_cors
import aiofiles
import imghdr
import pandas as pd
import os
from collections import deque, OrderedDict

abspath = os.path.abspath(__file__)
dname = os.path.dirname(abspath)
os.chdir(dname)

from collections import OrderedDict, MutableMapping

class Cache(MutableMapping):
    def __init__(self, maxlen, items=None):
        self._maxlen = maxlen
        self.d = OrderedDict()
        if items:
            for k, v in items:
                self[k] = v

    @property
    def maxlen(self):
        return self._maxlen

    def __getitem__(self, key):
        self.d.move_to_end(key)
        return self.d[key]

    def __setitem__(self, key, value):
        if key in self.d:
            self.d.move_to_end(key)
        elif len(self.d) == self.maxlen:
            self.d.popitem(last=False)
        self.d[key] = value

    def __delitem__(self, key):
        del self.d[key]

    def __iter__(self):
        return self.d.__iter__()

    def __len__(self):
        return len(self.d)

def image_resize(img, basewidth):
    wpercent = (basewidth/float(img.size[0]))
    hsize = int((float(img.size[1])*float(wpercent)))
    img = img.resize((basewidth,hsize), Image.ANTIALIAS)
    return img


class ImageDB:
    
    image_df = None
    
    def __init__ (self, df_path):
        self.names_cache = Cache(10)
        try:
            self.image_df = pd.read_pickle(df_path, 'gzip')
        except Exception as e:
            print(e)
            self.image_df = pd.DataFrame()

    def get_len(self):
        if self.image_df is not None:
            return len(self.image_df)
        else:
            return 0
        
    def return_file(self, file_id):
        file_data = {
            'filename': None,
            'image_format': None,
            'compress_file': None,
            'compress_format': None,
        }

        try:
            file_id = int(file_id)
            file_id = file_id%len(self.image_df)
            file_df = self.image_df.iloc[file_id]
            file_data['filename'] = file_df['filename']
            file_data['image_format'] = file_df['image_format']
            file_data['compress_file'] = file_df['compress_file']
            file_data['compress_format'] = file_df['compress_format']
        except Exception as e:
            file_data['filename'] = str(e)
        return file_data
    
    def return_ids_by_name(self, name):
        if name not in self.names_cache:
            ret_ids = self.image_df[self.image_df['filename'].str.contains(name, case=False, na = False)|
                                    self.image_df['compress_file'].str.contains(name, case=False, na = False)].index
            self.names_cache[name] = ret_ids
        else:
            ret_ids = self.names_cache[name]
        return ret_ids

async def get_image(request):
    req_size = None
    b64 = False
    req_ids = []
    images_b64 = []
    df_name = ''
    image_size = None
    if request.method == 'GET':
        try:
            image_req = request.match_info['image_req'].split('_')
            df_name = request.match_info['df_name']
        except:
            return web.Response(body='Wrong request', content_type='text/html')
    elif request.method == 'POST':
        try:
            data = await request.post()
            image_req = data['image_req'].split('_')
            df_name = data['df_name']
        except:
            return web.Response(body='Wrong request', content_type='text/html')

    if df_name not in request.app['image_dfs']:
        try:
            db_filename = './all_images_{}.picklegz'.format(df_name)
            print('open db with name {}'.format(db_filename))
            request.app['image_dfs'][df_name] = ImageDB(db_filename)
        except Exception as e:
            return web.Response(body='No DB File {}'.format(db_filename), content_type='text/html')

    images = []
    start_step = image_req[0].split(':')
    names_ids = None
    try:
        if start_step[0].isdigit():
            id_row = int(start_step[0])
        else:
            names_ids = request.app['image_dfs'][df_name].return_ids_by_name(start_step[0])
            id_row = names_ids[0]
    except Exception as e:
        id_row = 0
    if len(start_step) > 1:
        try:
            if start_step[1] == '':
                len_id = 1
            else:
                len_id = int(start_step[1])
            if len(start_step) > 2:
                start_id = int(start_step[2])
            else:
                start_id = 0
        except Exception as e:
            len_id = 1
            print(e)
        if names_ids is None:
            req_ids = [id_row+i for i in range(len_id)]
        else:
            if len(names_ids) > 0:
                start_id = start_id % len(names_ids)
                req_ids = names_ids[start_id:start_id+len_id]
            else:
                req_ids = [0]
    else:
        if len(start_step[0].split(',')) > 1:
            try:
                req_ids = [int(x) for x in start_step[0].split(',')]
            except Exception as e:
                print(e)
        else:
            req_ids = [id_row]

    if len(image_req) > 1:
        try:
            req_size = int(image_req[1])
        except Exception as e:
            pass
            # print(e)

        if len(image_req) > 2:
            try:
                b64 = int(image_req[2])
            except Exception as e:
                print(e)
    
    imgByteData = None
    if names_ids is None:
    	req_ids = req_ids[:20]
    else:
    	req_ids = req_ids[:50]
    for image_id in req_ids:
        test_db_file = request.app['image_dfs'][df_name].return_file(image_id)
        filename = test_db_file.get('filename', None)
        image_format = test_db_file.get('image_format', None)
        compress_file = test_db_file.get('compress_file', None)
        compress_format = test_db_file.get('compress_format', None)

        imgByteData = None

        if filename is not None:
            cache_key = (compress_file, filename)
            if cache_key in request.app['file_cache']:
                imgByteData = request.app['file_cache'][cache_key]
            else:
                if compress_format is not None:
                    archive_filename = compress_file
                    image_in_archive = filename
                    if compress_format.lower() == 'rar':
                        zf = rarfile.RarFile(archive_filename)
                    else:
                        zf = zipfile.ZipFile(archive_filename)
                    try:
                        imgByteData = zf.read(image_in_archive)
                        if imghdr.what(filename, h=imgByteData) is None:
                            filename = filename + ':no image.html'
                    except KeyError:
                        print('ERROR: Did not find {image_in_archive} in archive file')
                    except Exception as e:
                    	imgByteData = None
                    	filename = filename + ':no image.html'
                    	print(e)
                else:
                    if isfile(filename):
                        async with aiofiles.open(filename, mode='rb') as f:
                            imgByteData = await f.read()
                print(test_db_file, len(imgByteData))
                request.app['file_cache'][cache_key] = imgByteData
                if len(request.app['file_cache']) > 50:
                    remove_cache = request.app['file_cache'].popitem(last=False)
                    # print('remove {} from cache'.format(remove_cache))
                    
        if len(req_ids) > 1:
            if req_size is None:
                req_size = 1080
        
        if req_size is not None and req_size > 4000:
            req_size = 4000

        if req_size is not None and imgByteData is not None:
            if imghdr.what(filename, h=imgByteData) is not None:
                image = Image.open(io.BytesIO(imgByteData))
                image = image_resize(image, req_size).convert('RGB')
                imgByteArr = io.BytesIO()
                image.save(imgByteArr, format='JPEG')
                imgByteData = imgByteArr.getvalue()
                if len(req_ids) > 1:
                    images.append(image)
                print('resize to {} with len {}kb'.format(image.size, int(len(imgByteData)/1024)))
                image_size = 'w{}h{}'.format(image.size[0], image.size[1])

        if b64:
            if imgByteData is not None:
                new_image64 = {
                    'image':str(base64.b64encode(imgByteData))[2:-1], 
                    'image_df_id':image_id, 
                    'filename': filename,
                    'archive': compress_file,
                    'image_size': image_size,
                    }
            else:
                new_image64 = {
                    'image':'', 
                    'image_df_id':image_id, 
                    'filename': filename,
                    'archive': compress_file,
                    'image_size': image_size,
                    }
            images_b64.append(new_image64)
    
    if len(images) > 1 and not b64:
        widths, heights = zip(*(i.size for i in images))
        max_width = max(widths)
        total_height = sum(heights)
        new_im = Image.new('RGB', (max_width, total_height))

        y_offset = 0
        for im in images:
            new_im.paste(im, (0, y_offset))
            y_offset += im.size[1]
        imgByteArr = io.BytesIO()
        new_im.save(imgByteArr, format='JPEG')
        imgByteData = imgByteArr.getvalue()

    if imgByteData is not None or len(images_b64) > 0:
        if b64:
            return web.json_response(data=images_b64)
        else:
            if len(req_ids) == 1 and req_size is None:
                content_type = mimetypes.guess_type(filename)[0]
            else:
                content_type = 'image/jpeg'
            return web.Response(body=imgByteData, content_type=content_type)
    else:
        return web.Response(body='No image file', content_type='text/html')

async def get_df_len(request):
    df_len = 0
    df_name = './test.db'
    if request.method == 'GET':
        try:
            df_name = request.match_info['df_name']
            if df_name not in request.app['image_dfs']:
                request.app['image_dfs'][df_name] = ImageDB('./all_images_{}.picklegz'.format(df_name))
            
            df_len = request.app['image_dfs'][df_name].get_len()
        except:
            return web.Response(body='Wrong request', content_type='text/html')
    
    return web.json_response(data={'df_len': df_len})

app = web.Application()
app.add_routes([web.get('/imageml/id/{df_name}/{image_req}', get_image)])
app.add_routes([web.post('/imageml/id', get_image)])
app.add_routes([web.get('/imageml/df_len/{df_name}', get_df_len)])
app['image_dfs'] = {}
app['file_cache'] = OrderedDict()
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
    web.run_app(app, port=60007)