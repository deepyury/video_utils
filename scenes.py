import pickle
import numpy as np
import cv2
import itertools
from time import time
import json


class SceneDetector:

    def __init__(self, video_path):
        self.lines = 8
        self.columns = 8
        self.downscale = 8

        self.video_path = video_path.replace('\\', '/')
        self.name = self.video_path.split('/')[-1].split('.')[0]
        self.video = cv2.VideoCapture(video_path)
        self.frame_num = int(self.video.get(cv2.CAP_PROP_FRAME_COUNT))
        self.width = int(self.video.get(3))
        self.height = int(self.video.get(4))
        self.fps = int(self.video.get(5))
        self.exp_list = []
        self.exp_list_crops = []
        self.transition_list = [0, 0, 0, 0]

    def prepare_image(self, frame):
        h, w, _ = frame.shape
        crop_h, crop_w = (h // self.downscale, w // self.downscale)
        frame = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)

        assert h >= self.lines * crop_h, f'Height of frame ({h}) must be >= then lines * crop_h ({self.lines * crop_h})'
        assert w >= self.columns * crop_w, f'Width of frame ({w}) must be >= then columns * crop_w ({self.columns * crop_w})'

        crops = []
        h_pad = h - crop_h
        w_pad = w - crop_w
        h_dots = [int(h_pad / (self.lines - 1) * i) for i in range(self.lines)]
        w_dots = [int(w_pad / (self.columns - 1) * i) for i in range(self.columns)]
        for line in range(self.lines):
            for column in range(self.columns):
                y0 = h_dots[line]
                x0 = w_dots[column]
                y1 = y0 + crop_h
                x1 = x0 + crop_w
                crops.append(frame[y0: y1, x0: x1])

        return crops

    def postprocess(self, a, shot_length):
        b = []

        for (key, group) in itertools.groupby(a):
            group = list(group)
            if key == 1 and len(list(group)) > 1:
                group[1:] = [0] * (len(list(group)) - 1)
            b.append(group)

        c = []
        for (key, group) in itertools.groupby(list(itertools.chain.from_iterable(b))):
            group = list(group)
            if key == 0 and len(list(group)) <= shot_length:
                group[:] = [1] * len(list(group))
            c.append(group)

        d = []
        for (key, group) in itertools.groupby(list(itertools.chain.from_iterable(c))):
            group = list(group)
            if key == 1:
                if len(list(group)) <= shot_length:
                    group[1:] = [0] * (len(list(group)) - 1)
                else:
                    group[1:] = [0] * (len(list(group)) - 1)
                    group[-1] = 1
            d.append(group)

        return (list(itertools.chain.from_iterable(d)))

    def threshold(self, exps, thr, number):
        results = []
        for i in range(len(exps) - 1):
            crops = []
            for j in range(len(exps[i])):
                crops.append(1 if (abs(exps[i][j] - exps[i + 1][j]) > min(exps[i][j], exps[i + 1][j]) * thr) else 0)
            results.append(int(sum(crops) >= number))
        return results

    def disjunction(self, list1, list2):
        list3 = []
        for i in range(len(list1)):
            list3.append(int(list1[i] + list2[i]) > 0)
        return list3

    def get_fade(self, data):
        counter_plus = 0
        counter_minus = 0
        mean1, mean2, mean3, mean4, mean5 = data
        if mean1 - mean2 > max(mean1, mean2) * 0.05:
            counter_minus += 1
        if mean2 - mean3 > max(mean2, mean3) * 0.05:
            counter_minus += 1
        if mean3 - mean4 > max(mean3, mean4) * 0.05:
            counter_minus += 1
        if mean4 - mean5 > max(mean4, mean5) * 0.05:
            counter_minus += 1

        if mean1 - mean2 < max(mean1, mean2) * (-0.05):
            counter_plus += 1
        if mean2 - mean3 < max(mean2, mean3) * (-0.05):
            counter_plus += 1
        if mean3 - mean4 < max(mean3, mean4) * (-0.05):
            counter_plus += 1
        if mean4 - mean5 < max(mean4, mean5) * (-0.05):
            counter_plus += 1

        if counter_plus == 4:
            return 2
        elif counter_minus == 4:
            return 1
        else:
            return 0

    def process(self):
        start = time()

        frames = 0
        while True:
            ret, frame = self.video.read()
            if ret:
                print(f'{frames} / {self.frame_num}')
                self.exp_list.append(np.mean(cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)))
                if frames > 3:
                    self.transition_list.append(self.get_fade(self.exp_list))
                    self.exp_list.remove(self.exp_list[0])
                crops = self.prepare_image(frame)
                self.exp_list_crops.append([np.mean(crop) for crop in crops])
                frames+=1
            else:
                break
        self.video.release()

        with open('{}_results.txt'.format(self.name), 'wb+') as file:
            pickle.dump(self.exp_list_crops, file)
        with open('{}_fade.txt'.format(self.name), 'wb+') as file1:
            pickle.dump(self.transition_list, file1)

        self.flash_list = [0 if i == 2 else i for i in self.transition_list]
        self.fade_list = [1 if i == 2 else 0 for i in self.transition_list]
        results = self.threshold(self.exp_list_crops, 0.08, 20)

        # expositions = self.disjunction(results, self.fade_list)
        self.postprocessed = self.postprocess(results, 7)

        print(self.postprocessed)

        print(time()-start)

        result = {'fade_list': self.fade_list, 'flash_list': self.flash_list, 'postprocessed': self.postprocessed}
        with open(f'{self.name}_result.json', 'w') as f:
            json.dump(result, f)
        # self.show()


if __name__ == "__main__":
    video_path = r'/Users/yvkochn1/data/trailers_dataset/trailers/test_trailer/DETECTIVE CHINATOWN 3 Trailer (2020) Tony Jaa Action Comedy Movie.mp4'
    scenes = SceneDetector(video_path)
    scenes.process()
    raise NotImplemented
    # #
    # with open('DETECTIVE CHINATOWN 3 Trailer (2020) Tony Jaa Action Comedy Movie_result.json', 'r') as f:
    #     data = np.array(json.load(f)['postprocessed'])
    #
    # print(data)
    # starts = data[:, 0]
    # ends = data[:, 1]
    # print(starts)
    # print(ends)
    #
    # raise NotImplemented
