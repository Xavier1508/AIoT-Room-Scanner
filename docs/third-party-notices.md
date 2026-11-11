# Third-party notices

## Three.js

`tools/mapping/static/vendor/three.module.js` and `OrbitControls.js` are
vendored from Three.js **0.160.0** (MIT license, license text in
`tools/mapping/static/vendor/LICENSE`). They are served locally so the 3D
dashboard works without an internet connection.

## ESP_TF / TensorFlow Lite for Microcontrollers

`lib_deps = nickjgniklu/ESP_TF@2.1.1` supplies TensorFlow Lite for
Microcontrollers and Espressif ESP-NN kernels for the on-device empty/human
classifier. ESP_TF is MIT-licensed; TensorFlow Lite Micro is Apache-2.0.
The generated `src/ml_model_data.h` and `src/ml_model_metadata.h` are produced
from this project's own training data by `tools/mapping/ml/train.py`.

## VL53L1X register sequence

`src/sensors.cpp` contains a small self-contained register-level VL53L1X
implementation derived from the ST VL53L1X API and the Pololu VL53L1X Arduino
driver. It is used instead of adding a PlatformIO dependency during hardware
bring-up.

Copyright (c) 2017, STMicroelectronics  
Copyright (c) 2018–2022, Pololu Corporation

The applicable BSD 3-clause license is reproduced below:

> Redistribution and use in source and binary forms, with or without
> modification, are permitted provided that the following conditions are met:
>
> 1. Redistributions of source code must retain the above copyright notice,
>    this list of conditions and the following disclaimer.
>
> 2. Redistributions in binary form must reproduce the above copyright notice,
>    this list of conditions and the following disclaimer in the documentation
>    and/or other materials provided with the distribution.
>
> 3. Neither the name of the copyright holder nor the names of its contributors
>    may be used to endorse or promote products derived from this software
>    without specific prior written permission.
>
> THIS SOFTWARE IS PROVIDED BY THE COPYRIGHT HOLDERS AND CONTRIBUTORS “AS IS”
> AND ANY EXPRESS OR IMPLIED WARRANTIES, INCLUDING, BUT NOT LIMITED TO, THE
> IMPLIED WARRANTIES OF MERCHANTABILITY AND FITNESS FOR A PARTICULAR PURPOSE
> ARE DISCLAIMED. IN NO EVENT SHALL THE COPYRIGHT HOLDER OR CONTRIBUTORS BE
> LIABLE FOR ANY DIRECT, INDIRECT, INCIDENTAL, SPECIAL, EXEMPLARY, OR
> CONSEQUENTIAL DAMAGES (INCLUDING, BUT NOT LIMITED TO, PROCUREMENT OF
> SUBSTITUTE GOODS OR SERVICES; LOSS OF USE, DATA, OR PROFITS; OR BUSINESS
> INTERRUPTION) HOWEVER CAUSED AND ON ANY THEORY OF LIABILITY, WHETHER IN
> CONTRACT, STRICT LIABILITY, OR TORT (INCLUDING NEGLIGENCE OR OTHERWISE)
> ARISING IN ANY WAY OUT OF THE USE OF THIS SOFTWARE, EVEN IF ADVISED OF THE
> POSSIBILITY OF SUCH DAMAGE.
