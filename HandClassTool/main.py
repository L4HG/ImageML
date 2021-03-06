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
import requests
import uuid

warnings.simplefilter(action='ignore', category=FutureWarning)

abspath = os.path.abspath(__file__)
dname = os.path.dirname(abspath)
os.chdir(dname)


def image_resize(img, basewidth):
    wpercent = (basewidth/float(img.size[0]))
    hsize = int((float(img.size[1])*float(wpercent)))
    img = img.resize((basewidth,hsize), Image.ANTIALIAS)
    return img

# db_conn = 'file_list_store.db'
# db_conn = 'file_list_pho.db'

create_table_q = '''
                    CREATE TABLE IF NOT EXISTS file_classes (
                        file_id TEXT, 
                        file_name TEXT,
                        class TEXT,
                        coords TEXT,
                        image_size TEXT,
                        time_to_select int,
                        user_id TEXT,
                        class_type TEXT,  
                        df_name TEXT,
                        datetime int);
                '''
add_class_q = '''
                    INSERT INTO file_classes (
                        file_id,
                        file_name, 
                        class,
                        coords,
                        image_size, 
                        time_to_select,
                        user_id,
                        class_type,
                        df_name,
                        datetime
                    ) VALUES (
                        ?,?,?,?,?,?,?,?,?,strftime('%s','now')
                    )
            '''
get_current_file_q = '''
                    SELECT file_id FROM file_classes WHERE df_name=? and user_id=?
                    '''

class PoolConnection:
    current_conn = None
    db_name = None
    db_file = None

    def __init__(self, db_name):
        self.db_file = 'file_list_{}.dbsqlite'.format('main')
        self.db_name = db_name

    def get_conn(self):
        if self.current_conn is not None:
            return self.current_conn
        else:
            self.curren_conn = sqlite3.connect(self.db_file)
            return self.curren_conn
        
    def create_tables(self):
        current_conn = self.get_conn()
        cursor = current_conn.cursor()
        cursor.execute(create_table_q)
        current_conn.commit()
        cursor.close()

    def get_next_ids(self, max_id, user_id):
        current_conn = self.get_conn()
        cursor = current_conn.cursor()
        cursor.execute(get_current_file_q, (self.db_name, user_id))
        current_ids = np.array(cursor.fetchall(), dtype=np.uint32)
        cursor.close()
        if len(current_ids) > 0:
            start_array = np.arange(max_id, dtype=np.uint32)
            start_array = np.setdiff1d(start_array, current_ids, assume_unique=True)
            np.random.shuffle(start_array)
            out = start_array
        else:
            out = np.arange(max_id, dtype=np.uint32)
            np.random.shuffle(out)
        return out

async def get_html(request):
    if request.method == 'GET':
        try:
            df_name = request.match_info['df_name']
        except:
            return web.Response(body='Wrong request', content_type='text/html')

    user_id = request.cookies.get('user_id', None)
    if user_id is None:
            user_id = str(uuid.uuid4())
    if df_name not in request.app['db_pool']:
        request.app['db_pool'][df_name] = PoolConnection(df_name)
        request.app['db_pool'][df_name].create_tables()
    
    ret_resp = web.FileResponse('index.html')
    ret_resp.set_cookie('user_id', user_id)
    return ret_resp

async def get_ids_for_cache(request):
    if request.method == 'GET':
        try:
            df_name = request.match_info['df_name']
        except:
            return web.Response(body='Wrong request', content_type='text/html')
    step = 7

    user_id = request.cookies.get('user_id', None)
    if user_id is not None:
        user_db_id = (df_name, user_id)
        if user_db_id not in request.app['shuffle_list']:
            print('user {} get ids for {}'.format(user_id, df_name))
            resp_len = requests.get('https://home.namezis.com/imageml/df_len/{}'.format(df_name))
            try:
                max_len_id = int(resp_len.json()['df_len'])
            except Exception as e:
                print(e)
                max_len_id = 0
            request.app['shuffle_list'][user_db_id] = request.app['db_pool'][df_name].get_next_ids(max_len_id, user_id)
            request.app['last_file_ids'][user_db_id] = []

        if len(request.app['return_ids'].get(user_db_id, [])) > 0:
            ret_ids = request.app['return_ids'][user_db_id]
            request.app['return_ids'][user_db_id] = []
        else:
            ret_ids = request.app['shuffle_list'][user_db_id][:step]
    else:
        print('no user id for next ids')
        ret_ids = []
    # print(ret_ids)
    return web.json_response(data=ret_ids.tolist())

async def set_class(request):
    ret_data = {'result':'bad', 'file_id': 1}
    try:
        data = await request.post()
        user_id = request.cookies.get('user_id', None)
        if user_id is None:
            return web.json_response(data={'result':'no user id for set class'} )
        df_name = data['df_name']
        file_id = data['file_id']
        file_name = data['file_name']
        file_class = data['file_class']
        image_size = data['image_size']
        time_to_select = data['time_to_select']
        class_type = data['class_type']
        # print(file_id, file_name, file_class, user_id, df_name)
        # print(data)
        file_coords = data['coords']
        user_db_id = (df_name, user_id)
        try:
            request.app['last_file_ids'][user_db_id].append((int(file_id), file_name))
        except:
            pass
        if file_class == 'Вернуть прошлое фото' and len(request.app['last_file_ids'][user_db_id]) > 1:
            last_ids_np = np.array((request.app['last_file_ids'][user_db_id][-1][0], 
                                    request.app['last_file_ids'][user_db_id][-2][0]))
            request.app['return_ids'][user_db_id] = last_ids_np
            return web.json_response(data={'result':'good', 'file_id': last_ids_np.tolist()})
        else:
            if len(file_id) > 0:
                request.app['shuffle_list'][user_db_id] = request.app['shuffle_list'][user_db_id][1:]

        if len(file_id) > 0:
            current_conn = request.app['db_pool'][df_name].get_conn()
            cursor = current_conn.cursor()
            cursor.execute(add_class_q, (
                file_id, file_name, 
                file_class, file_coords, 
                image_size, time_to_select,
                user_id, 
                class_type,  df_name,
                ))
            current_conn.commit()
            cursor.close()
        ret_data['result'] = 'good'
    except Exception as e:
        ret_data = {'result':str(e), 'file_id': 0}
    ret_resp = web.json_response(data=ret_data )
    ret_resp.set_cookie('user_id', user_id)
    return ret_resp


app = web.Application()
app['db_pool'] = {}
app['shuffle_list'] = {}
app['last_file_ids'] = {} 
app['return_ids'] = {}
app.add_routes([web.get('/image_this/html/{df_name}', get_html)])
app.add_routes([web.get('/image_this/get_ids/{df_name}', get_ids_for_cache)])
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
