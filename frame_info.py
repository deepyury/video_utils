import numpy as np
import cv2


def add_text_to_frame(frame: [np.ndarray], text: [list, str]) -> np.ndarray:
    h, w, _ = frame.shape
    font = cv2.FONT_HERSHEY_SIMPLEX
    x, y = int(w * 0.01), int(h * 0.5)
    y_pad = int(h * 0.05)
    font_scale = h / 1080
    font_color = (255, 153, 255)
    line_type = int(h // 1000 + 1)

    def put_text(i, t_):
        cv2.putText(frame, t_, (x, y + y_pad * i), font, font_scale, font_color, line_type)
        return i + 1

    if isinstance(text, str):
        text = [text]
    line = 0
    for t in text:
        line = put_text(line, t)
    return frame
