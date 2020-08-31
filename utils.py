import codecs
import glob
import hashlib
import os
import platform
import subprocess
import sys
from copy import deepcopy
import numpy as np

import yaml

WINDOWS = platform.system() not in {'Darwin', 'linux'}
MAC = platform.system() == 'Darwin'
FFMPEG = 'ffmpeg'
FFPROBE = 'ffprobe'


def correct_path(path):
    if WINDOWS:
        return path.replace(os.sep, '/')
    return path


def make_folder(folder, hidden=False):
    if not os.path.exists(folder):
        os.makedirs(folder)
    if hidden:
        if WINDOWS:
            subprocess.call(["attrib", "+H", folder])
        else:
            subprocess.call(["chflags", "hidden", folder])


def get_all_filenames(paths: [list, str, tuple], extensions: tuple, exclude_path: str = None) -> list:
    filenames = []

    if isinstance(paths, str):
        if os.path.isfile(paths):
            filenames.append(correct_path(paths))
            return filenames
        else:
            paths = [paths]

    for path in paths:
        files = glob.glob(os.path.join(path, '**/*.*'), recursive=True) if os.path.isdir(path) else [path]
        for file in files:
            if file.lower().endswith(extensions):
                if exclude_path is not None:
                    if not correct_path(file).startswith(correct_path(exclude_path)):
                        filenames.append(correct_path(file))
                else:
                    filenames.append(correct_path(file))

    return filenames


def get_sha256(string):
    m = hashlib.sha256()
    m.update(string.encode())
    return m.hexdigest()


def frame_skip_ratio(input_fps, target_fps):
    return max(1, int(input_fps // target_fps))


def find_min_possible_fps(fps):
    while fps > 25:
        if 12.5 < fps / 2 < 25:
            break
        fps /= 2
    return fps


class YamlLinker:
    def __init__(self, d):
        self.d = deepcopy(d)

    def get_value(self, d, path):
        key = path.pop(0)
        v = d[key]
        if len(path) != 0:
            return self.get_value(v, path)
        else:
            return v

    def find_end_value(self, value):
        if isinstance(value, str) and value.startswith('@'):
            v = self.get_value(self.d, value[1:].split('.'))
            return self.find_end_value(v)
        else:
            return value

    def set_links(self, d):
        for k, v in d.items():
            if isinstance(v, dict):
                self.set_links(v)
            elif isinstance(v, str):
                d[k] = self.find_end_value(v)

    def __call__(self):
        self.set_links(self.d)
        return self.d


def load_config(path, link=True):
    """For YAML configs"""
    with codecs.open(path, 'r', 'utf-8') as file:
        data = yaml.safe_load(file)
    if link:
        data = YamlLinker(data)()
    return data


def get_paths_root(paths):
    def commonprefix(args, sep='/'):
        return os.path.commonprefix(args).rpartition(sep)[0]
    paths = [paths] if isinstance(paths, str) else paths
    paths = [correct_path(p) for p in paths]
    dirnames = [el if os.path.isdir(el) else f'{os.path.dirname(el)}{os.sep}' for el in paths]
    dirnames = [correct_path(p) for p in dirnames]
    dirname = commonprefix(dirnames, os.sep) or commonprefix(dirnames, '/') if len(dirnames) > 1 else dirnames[0]
    dirname = dirname[:-1] if dirname.endswith(('/', '\\')) else dirname
    return dirname
