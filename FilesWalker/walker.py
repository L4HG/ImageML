from pathlib import Path

import imghdr
import zipfile
import rarfile
import math
from tqdm import tqdm
import pandas as pd

db_path = '/test'

path = Path(db_path)
all_files = path.rglob('*')

all_images = []

for i, file_posix in enumerate(all_files):
    if not file_posix.is_file():
        continue
    filename = str(file_posix.absolute())
    img_format = imghdr.what(filename)
    if img_format is not None:
        new_image = {
                    'filename': None,
                    'image_format': None,
                    'compress_file': None,
                    'compress_format': None,
                }
        new_image['filename'] = filename
        new_image['image_format'] = img_format
        all_images.append(new_image)
    else:
        is_zip = zipfile.is_zipfile(filename)
        if is_zip:
            inner_filelist = []
            try:
                zip_file = zipfile.ZipFile(filename)
                for inner_file in zip_file.namelist():
                    new_image = {
                        'filename': None,
                        'image_format': None,
                        'compress_file': None,
                        'compress_format': None,
                    }
                    new_image['filename'] = inner_file
                    new_image['compress_file'] = filename
                    new_image['compress_format'] = 'zip'
                    all_images.append(new_image)
            except Exception as e:
                print(filename, e)
                
        try:
            is_rar = rarfile.is_rarfile(filename)
        except Exception as e:
            is_rar = False

        if is_rar:
            inner_filelist = []
            try:
                rar_file = rarfile.RarFile(filename)
                for inner_file in rar_file.namelist():
                    new_image = {
                        'filename': None,
                        'image_format': None,
                        'compress_file': None,
                        'compress_format': None,
                    }
                    new_image['filename'] = inner_file
                    new_image['compress_file'] = filename
                    new_image['compress_format'] = 'rar'
                    all_images.append(new_image)
            except Exception as e:
                print(filename, e)
images_pd = pd.DataFrame(all_images)

images_df_file = 'all_images_{}.picklegz'.format(db_path.lower().split('/')[-1])

images_pd.to_pickle(images_df_file, compression='gzip')