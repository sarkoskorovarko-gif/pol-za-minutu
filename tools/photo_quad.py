"""Помощник разметки фото: по двум точкам схода (линии вдоль стен) и углу
комнаты считает 4 точки прямоугольника на полу и его размер в метрах.
Используется для черновой разметки; дальше точки правятся на странице tools/markup.html.
"""
import numpy as np


def floor_quad(img_size, VA, VB, O, PA, PB, ref, ref_m):
    """VA, VB — точки схода двух перпендикулярных направлений пола (пиксели).
    O — угол комнаты на полу; PA — точка на линии O→VA (вдоль первой стены);
    PB — точка на линии O→VB; ref — две точки на полу, между которыми ref_m метров.
    Возвращает quad (4 точки: O, по A, дальний, по B) и размер [W, D] в метрах."""
    w, h = img_size
    c = np.array([w / 2, h / 2])
    va, vb = np.array(VA, float) - c, np.array(VB, float) - c
    f = np.sqrt(max(1.0, -va.dot(vb)))                  # фокус из ортогональности направлений
    K = np.array([[f, 0, c[0]], [0, f, c[1]], [0, 0, 1]])
    Ki = np.linalg.inv(K)
    r1 = Ki @ np.array([*VA, 1.0]); r1 /= np.linalg.norm(r1)
    r2 = Ki @ np.array([*VB, 1.0]); r2 /= np.linalg.norm(r2)
    t = Ki @ np.array([*O, 1.0])
    H = K @ np.column_stack([r1, r2, t])               # (a, b) на полу → пиксели
    Hi = np.linalg.inv(H)

    def to_floor(p):
        q = Hi @ np.array([*p, 1.0]); return q[:2] / q[2]

    def to_img(a, b):
        q = H @ np.array([a, b, 1.0]); return q[:2] / q[2]

    s = ref_m / np.linalg.norm(to_floor(ref[0]) - to_floor(ref[1]))  # метров на единицу
    A = abs(to_floor(PA)[0]); B = abs(to_floor(PB)[1])
    sa, sb = np.sign(to_floor(PA)[0]), np.sign(to_floor(PB)[1])
    quad = [to_img(0, 0), to_img(sa * A, 0), to_img(sa * A, sb * B), to_img(0, sb * B)]
    return [[round(float(x), 1), round(float(y), 1)] for x, y in quad], [round(A * s, 2), round(B * s, 2)], round(float(f))

