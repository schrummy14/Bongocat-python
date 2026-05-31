import numpy as np
import matplotlib.pyplot as plt
from PIL import Image

FILES = (
    "texture/bg.npy",
    "texture/cat.npy",
    "texture/hand.npy",
    "texture/mouse.npy",
    "keyboard/0.npy"
)

for f in FILES:
    try:
        img = np.load(f"{f}")

        cov = (img*255).astype(np.uint8)

        out = Image.fromarray(cov)

        out.show()

        # plt.imshow(img)

        # plt.show()
    except Exception as e:
        print(e)
