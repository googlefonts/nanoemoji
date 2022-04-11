# Copyright 2020 Google LLC
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
import os
from pathlib import Path
from PIL import Image
from typing import Tuple, Union


class PNG(bytes):

    # The first eight bytes of a PNG file always contain the following (decimal) values:
    #   137 80 78 71 13 10 26 10
    # https://www.w3.org/TR/PNG-Structure.html
    SIGNATURE = b"\x89PNG\r\n\x1a\n"

    def __new__(cls, *args, **kwargs):
        self = super().__new__(cls, *args, **kwargs)
        header = self[:8]
        if header != cls.SIGNATURE:
            raise ValueError("Invalid PNG file: bad signature {header!r}")
        self._size = None
        return self

    @property
    def size(self) -> Tuple[int, int]:
        if self._size is None:
            with Image.open(BytesIO(self)) as image:
                self._size = image.size
        return self._size

    @classmethod
    def read_from(cls, path: Union[str, os.PathLike]) -> "PNG":
        return cls(Path(path).read_bytes())
