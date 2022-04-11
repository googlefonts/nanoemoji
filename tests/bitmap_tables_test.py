# Copyright 2022 Google LLC
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#      http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

from io import BytesIO
from nanoemoji.color_glyph import ColorGlyph
from nanoemoji import config
from nanoemoji.bitmap_tables import _cbdt_bitmap_data, BitmapMetrics
from nanoemoji.png import PNG
from PIL import Image
from test_helper import *


def test_bitmap_data_for_non_square_image():
    font_config = config.load()
    image_bytes = BytesIO()
    Image.new("RGBA", (90, 120), color="red").save(image_bytes, format="png")
    image_bytes.seek(0)
    image_bytes = image_bytes.read()
    png = PNG(image_bytes)

    metrics = BitmapMetrics.create(font_config, png, 120)
    cbdt_bitmap = _cbdt_bitmap_data(font_config, metrics, png)
    assert (cbdt_bitmap.metrics.width, cbdt_bitmap.metrics.height) == (90, 120)
