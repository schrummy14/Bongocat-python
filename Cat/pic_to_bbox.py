import numpy as np
import psd_tools

# psd_path = 'cat.psd'
psd_path = 'PSD/mousebg.psd'
psd = psd_tools.PSDImage.open(psd_path)
print(psd)
for l in psd:
	print(f"{l.name}: {np.array(l.bbox)}")
