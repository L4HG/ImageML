import sqlite3
import random
import io
from aiohttp import web
import pandas as pd
import aiohttp_cors
from PIL import Image
import base64
import os
import numpy as np
import warnings

warnings.simplefilter(action='ignore', category=FutureWarning)

abspath = os.path.abspath(__file__)
dname = os.path.dirname(abspath)
os.chdir(dname)


def image_resize(img, basewidth):
    wpercent = (basewidth/float(img.size[0]))
    hsize = int((float(img.size[1])*float(wpercent)))
    img = img.resize((basewidth,hsize), Image.ANTIALIAS)
    return img

db_conn = 'file_list_store.db'

create_table_q = '''
                    CREATE TABLE IF NOT EXISTS file_classes (
                        file_id TEXT, 
                        file_name TEXT,
                        class TEXT,
                        coords TEXT,
                        datetime class_at int);
                '''
add_class_q = '''
                    INSERT INTO file_classes (
                        file_id,
                        file_name, 
                        class,
                        coords, 
                        datetime
                    ) VALUES (
                        ?,?,?,?,strftime('%s','now')
                    )
            '''
get_current_file_q = '''
                    SELECT file_id FROM file_classes
                    '''

class PoolConnection:
    current_conn = None
    def get_conn(self):
        if self.current_conn is not None:
            return self.current_conn
        else:
            self.curren_conn = sqlite3.connect(db_conn)
            return self.curren_conn
        
    def create_tables(self):
        current_conn = self.get_conn()
        cursor = current_conn.cursor()
        cursor.execute(create_table_q)
        current_conn.commit()
        cursor.close()

    def get_next_ids(self, max_id):
        current_conn = self.get_conn()
        cursor = current_conn.cursor()
        cursor.execute(get_current_file_q)
        current_ids = np.array(cursor.fetchall())
        cursor.close()
        if len(current_ids) > 0:
            start_array = np.arange(max_id, dtype=np.uint32)
            np.random.shuffle(start_array)
            out = start_array[np.isin(start_array, current_ids, invert=True)]
        else:
            out = np.arange(max_id, dtype=np.uint32)
            np.random.shuffle(out)
        return out

async def get_html(request):
    if len(request.app['db_pool']) == 0:
        request.app['db_pool'].append(PoolConnection())
        request.app['db_pool'][0].create_tables()
    return web.FileResponse('index.html')

async def get_ids_for_cache(request):
    step = 5
    if len(request.app['shuffle_list']) == 0:
        request.app['shuffle_list'].append(request.app['db_pool'][0].get_next_ids(7600000))
    ret_ids, request.app['shuffle_list'][0] = request.app['shuffle_list'][0][:step], request.app['shuffle_list'][0][step:]
    return web.json_response(data=ret_ids.tolist())

async def set_class(request):
    noup = 1
    ret_data = {'result':'bad', 'file_id': 1}
    try:
        data = await request.post()
        file_id = data['file_id']
        file_name = data['file_name']
        file_class = data['file_class']
        print(file_id, file_class)
        file_coords = data['coords']
        if len(file_id) > 0:
            current_conn = request.app['db_pool'][0].get_conn()
            cursor = current_conn.cursor()
            cursor.execute(add_class_q, (file_id, file_name, file_class, file_coords))
            current_conn.commit()
            cursor.close()
        ret_data['result'] = 'good'
    except Exception as e:
        ret_data = {'result':str(e), 'file_id': 0}
    return web.json_response(data=ret_data)


app = web.Application()
app['db_pool'] = []
app['shuffle_list'] = []
app.add_routes([web.get('/image_this', get_html)])
app.add_routes([web.get('/image_this/get_ids', get_ids_for_cache)])
app.add_routes([web.post('/image_this/set_class', set_class)])

# Configure default CORS settings.
cors = aiohttp_cors.setup(app, defaults={
    "*": aiohttp_cors.ResourceOptions(
            allow_credentials=True,
            expose_headers="*",
            allow_headers="*",
        )
})

# Configure CORS on all routes.
for route in list(app.router.routes()):
    cors.add(route)

if __name__ == '__main__':
    web.run_app(app, port=60005)
