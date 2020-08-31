import json
import os
import pickle
import subprocess
import cv2
import pydub.utils as mdinfo

from utils import MAC, FFPROBE

if MAC:
    mdinfo.get_prober_name = lambda: FFPROBE
mdinfo = mdinfo.mediainfo


class Video:
    # statuses:
    INITIATED = 0
    METACOLLECTED = 1
    PROCESSED = 2
    POSTPROCESSED = 3
    ERRORED = 10
    DEFECTIVE = 11

    def __init__(self, path, cached, cache_dir=None, root_dir=None, min_fps=0, min_duration=0):
        self.path = path
        self.cached = cached
        self.min_fps = min_fps
        self.min_duration = min_duration

        root_dir = root_dir or os.path.dirname(path)
        relate_path = path.replace(root_dir, '')[1:]
        relate_path = relate_path.replace('/', '.')

        self.store_meta_path = os.path.join(cache_dir, relate_path + '.meta')
        self.store_data_path = os.path.join(cache_dir, relate_path + '.data')

        self.meta = {}
        self._data = {}
        self.status = self.INITIATED

        if self.cached and not os.path.exists(self.store_meta_path):
            self.cached = False
            print(f'Dump file `{self.store_meta_path}` for video `{self.path}` is not exist while cached=True. '
                  f'Video will initiate from scratch')

        if self.cached:
            self.cached = self.load_meta_and_status()

        if not self.cached:
            self.cap = cv2.VideoCapture(self.path)
            if self.fps < self.min_fps or self.duration < self.min_duration:
                self.status = self.DEFECTIVE

    def __repr__(self):
        return (f'{self.__class__.__name__}('
                f'path="{self.path}", status={self.status}, cached={self.cached}, '
                f'fps={self.meta.get("fps")}, frame_num={self.meta.get("frame_num")}, '
                f'duration={self.meta.get("duration")}, '
                f'width={self.meta.get("width")}, height={self.meta.get("height")}, '
                f'datetime="{self.meta.get("datetime")}", is_gopro={self.meta.get("is_gopro")}, '
                f'is_variable_fps="{self.meta.get("is_variable_fps")}", rotation={self.meta.get("rotation")}, '
                f'data(keys only)={self.data.keys()}, data(lens of keys)={[len(v) for v in self.data.values()]})'
                f')')

    def init_cap(self):
        self.cap = cv2.VideoCapture(self.path)

    def save_meta(self):
        self.meta.update({
            'fps': self.fps,
            'frame_num': self.frame_num,
            'duration': self.duration,
            'width': self.width,
            'height': self.height,
            'is_gopro': self.is_gopro,
            'is_variable_fps': self.is_variable_fps,
            'rotation': self.rotation,
            'mediainfo': self.mediainfo,
            'datetime': self.datetime
        })
        if self.is_variable_fps:
            self.meta.update({'frames_timecodes': self.frames_timecodes})

        with open(self.store_meta_path, 'wb') as file:
            pickle.dump([self.meta, self.status], file)
        if hasattr(self, 'cap'):
            # We need in self.cap only to collect meta for first time
            # (if instance of Video isn't from dump otherwise self.cap does not exist in Video)
            self.cap.release()
            del self.cap
        self.status = max(self.METACOLLECTED, self.status)

    def set_status(self, status, save=True):
        self.status = status
        if save:
            self.save_meta()

    def load_meta_and_status(self):
        assert os.path.exists(self.store_meta_path), f'Path for meta `{self.store_meta_path}` ' \
            f'of video {self.path} must be exist.'
        try:
            with open(self.store_meta_path, 'rb') as file:
                self.meta, self.status = pickle.load(file)
                return True
        except:
            return False

    def save_data(self):
        with open(self.store_data_path, 'wb') as file:
            pickle.dump(self._data, file)
        self._data = {}
        self.cached = True

    def load_data(self):
        if not os.path.exists(self.store_data_path):
            return

        with open(self.store_data_path, 'rb') as file:
            self._data = pickle.load(file)
        self.cached = False

    def update_data(self, key, data, add_type='last', save=True):
        assert add_type in ['last', 'full'], f'Wrong add_type `{add_type}` in Video.update_data'

        if data is None:
            return True

        if save and os.path.exists(self.store_data_path):
            self.load_data()

        if add_type == 'last':
            if key not in self._data:
                self._data[key] = []
            self._data[key].append(data)
        elif add_type == 'full':
            self._data[key] = data

        if save:
            self.save_data()

    @property
    def data(self):
        if self.cached:
            self.load_data()
        return self._data

    def get_data(self, keys: [list, str]):
        keys = [keys] if isinstance(keys, str) else keys
        result = []
        for key in keys:
            try:
                result.append(self.data.get(key))
            except Exception as e:
                raise RuntimeError
        return result[0] if len(keys) == 1 else result

    @property
    def mediainfo(self):
        if self.meta.get('mediainfo') is None:
            self.meta['mediainfo'] = mdinfo(self.path)
        return self.meta['mediainfo']

    @property
    def fps(self):
        if self.meta.get('fps') is None:
            self.meta['fps'] = self.cap.get(cv2.CAP_PROP_FPS)
        return self.meta['fps']

    @property
    def frame_num(self):
        if self.meta.get('frame_num') is None:
            self.meta['frame_num'] = int(self.cap.get(cv2.CAP_PROP_FRAME_COUNT))
        return self.meta['frame_num']

    @property
    def duration(self):
        # TODO: возможно лушче использовать последнее значение в self.frames_timecodes
        return self.frame_num / self.fps if self.fps > 0 else 0

    @property
    def width(self):
        if self.meta.get('width') is None:
            self.meta['width'] = self.cap.get(cv2.CAP_PROP_FRAME_WIDTH)
        return self.meta['width']

    @property
    def height(self):
        if self.meta.get('height') is None:
            self.meta['height'] = self.cap.get(cv2.CAP_PROP_FRAME_HEIGHT)
        return self.meta['height']

    @property
    def is_gopro(self):
        # --- using pydub (ffprobe) or mediainfo ---

        # def mediainfo_util():
        #     proc = subprocess.Popen(f'{MEDIAINFO} --Inform="Video;%Title%" "{self.path}"',
        #                             stdout=subprocess.PIPE, shell=True)
        #     (out, err) = proc.communicate()
        #     if err:
        #         return False
        #     return 'gopro' in out.decode('utf-8').lower()

        def ffprobe_util():
            try:
                return 'gopro' in self.mediainfo['TAG']['encoder'].lower()
            except:
                return None

        if self.meta.get('is_gopro') is None:
            self.meta['is_gopro'] = ffprobe_util()  # or mediainfo_util()
        return self.meta['is_gopro']

    @property
    def is_variable_fps(self):
        if self.meta.get('is_variable_fps') is None:
            command = f'{FFPROBE} -v quiet -print_format json -show_streams "{self.path}"'
            proc = subprocess.Popen(command, stdout=subprocess.PIPE, shell=True)
            (out, err) = proc.communicate()
            if err:
                raise RuntimeError
            data = json.loads(out)
            self.meta['is_variable_fps'] = int(data['streams'][0]['avg_frame_rate'].split('/')[-1]) not in [1, 1001]
        return self.meta['is_variable_fps']

    @property
    def frames_timecodes(self):
        if self.meta.get('frames_timecodes') is None:
            command = f'{FFPROBE} -v quiet -print_format json -show_entries packet=pts_time,duration_time,stream_index "{self.path}"'
            proc = subprocess.Popen(command, stdout=subprocess.PIPE, shell=True)
            (out, err) = proc.communicate()
            if err:
                raise RuntimeError
            data = json.loads(out)
            stream_0 = [float(i['pts_time']) for i in data['packets'] if i['stream_index'] == 0]
            self.meta['frames_timecodes'] = stream_0
        return self.meta['frames_timecodes']

    @property
    def rotation(self):
        if self.meta.get('rotation') is None:
            command = f'{FFPROBE} -loglevel error -select_streams v:0 -show_entries stream_tags=rotate -of default=nw=1:nk=1 -i "{self.path}"'
            proc = subprocess.Popen(command, stdout=subprocess.PIPE, shell=True)
            (out, err) = proc.communicate()
            if err:
                raise RuntimeError
            if out.decode("utf-8") is not '':
                data = int(json.loads(out))
                if data not in [90, 180, 270]:
                    data = 0
            else:
                data = 0
            self.meta['rotation'] = data
        return self.meta['rotation']

    @property
    def datetime(self):
        # --- using pydub (ffprobe) or mediainfo ---

        # def mediainfo_util():
        #     proc = subprocess.Popen(f'{MEDIAINFO} --Inform="General;%Recorded_Date%" "{self.path}"',
        #                             stdout=subprocess.PIPE, shell=True)
        #     (out, err) = proc.communicate()
        #     if err:
        #         raise RuntimeError
        #     _dt = out.decode('utf-8')[:ref_len].replace('-', ':')
        #     if len(_dt) != ref_len:
        #         raise ValueError
        #     return _dt

        def ffprobe_util():
            # for k, v in self.mediainfo.items():
            #     print(k, v)
            _dt = self.mediainfo['TAG']['creation_time']
            _dt = _dt[:ref_len].replace('-', ':').replace('T', ' ')
            date = self.mediainfo['TAG'].get('date')
            if date is not None and len(_dt) != ref_len:
                _dt = f"{date.replace('-', ':')} {_dt}"
            if len(_dt) != ref_len:
                raise ValueError
            return _dt

        if self.meta.get('datetime') is None:
            _datetime = '1970:01:01 00:00:00'
            ref_len = len(_datetime)
            for func in [ffprobe_util]:
                try:
                    _datetime = func()
                except:
                    pass
            self.meta['datetime'] = _datetime
        return self.meta['datetime']



