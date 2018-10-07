#!/usr/bin/python3
from core.Global import *
from core.core import Core
from nippon.f209 import F209
from core.device_finder import DeviceFinder

if __name__ == '__main__':
    Core({
        'np': F209(),
        })

    DeviceFinder.launch_device_finder()

    np = Core.modules['np']

    for _ in range(60):
        if not Global.run: break
        sts = np.get_status()
        sleep(1)
    # break
    Core.quit()

    # reports
    print('='*80)
    print('='*80)
    print('DONE')
    print('='*80)
    print('='*80)
    input('                             Press any key...')

