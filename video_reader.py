import os
import cv2
import traceback
from threading import Thread
from queue import Queue
from math import ceil

from time import sleep, time
from utils import frame_skip_ratio


class VideoReader:
    def __init__(self, video, target_fps=25, start_frame=None, end_frame=None, size=None, buffer_maxsize=200):
        self.video = video
        self.start_frame = start_frame or 0
        self.end_frame = end_frame or self.video.frame_num
        self.size = tuple(size) if size is not None else None
        self.target_fps = target_fps
        self.skip_rate = frame_skip_ratio(self.video.fps, self.target_fps)

        self.cap = cv2.VideoCapture(self.video.path)
        self._init_thread(buffer_maxsize)
        self.frame_counter = 0

    def generator(self, stats=None):
        """ Return BGR frame """
        while self.frame_counter < self.video.frame_num:
            if stats is not None:
                _start_time = time()

            frame = self.next_thread()
            if self.frame_counter % self.skip_rate == 0:
                self.frame_counter += 1
                yield frame
            else:
                self.frame_counter += 1

    def __len__(self):
        return ceil(self.video.frame_num / self.skip_rate)

    def _init_thread(self, maxsize):
        self.done = False
        self.frame_queue = Queue(maxsize=maxsize)
        self._start_thread()

    def read_video(self, time_lag=0.1):
        try:
            frame_id = self.start_frame
            if self.start_frame > 0:
                self.cap.set(1, self.start_frame)  # set frame position to start read frames from

            while frame_id < self.end_frame:
                if self.frame_queue.full():
                    sleep(time_lag)
                else:
                    ret, frame = self.cap.read()
                    if frame is None:
                        if self.video.is_gopro:
                            # to solve problem with None frames of GoPro video
                            # https://stackoverflow.com/questions/49060054/opencv-videocapture-closes-with-videos-from-gopro
                            continue
                        else:
                            self.done = True
                            return None
                    if self.size is not None:
                        frame = cv2.resize(frame, self.size)
                    self.frame_queue.put(frame)
                    frame_id += 1
            self.done = True

        except (KeyboardInterrupt, SystemExit):
            self.done = True
            raise
        except Exception as ex:
            self.done = True
            # self.logger.error('ERROR in VideoReader -> start_thread: {}'.format(traceback.format_exc()))
            raise

    def _start_thread(self):
        self.thread_video_reading = Thread(target=self.read_video, args=(), daemon=True)
        self.thread_video_reading.start()
        sleep(0.5)

    def next_thread(self):
        start_time = time()
        last_start_time = start_time
        while True:
            if self.frame_queue.empty():
                if not self.thread_video_reading.is_alive():
                    return None
                else:
                    if (time() - last_start_time) > 1:
                        # self.logger.warning(f'Empty frame_queue in VideoReader -> next_thread '
                        #                     f'for {time() - start_time} seconds')
                        last_start_time = time()
                    sleep(0.1)
            else:
                return self.frame_queue.get()
