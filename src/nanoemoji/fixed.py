# Copyright 2021 Google LLC
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

from picosvg.geometric_types import almost_equal


MIN_INT16 = -(1 << 15)
MAX_INT16 = (1 << 15) - 1

MIN_UINT16 = 0
MAX_UINT16 = (1 << 16) - 1

MIN_F2DOT14 = -2.0
MAX_F2DOT14 = MAX_INT16 / (1 << 14)

MIN_FIXED = MIN_INT16
MAX_FIXED = ((1 << 31) - 1) / (1 << 16)


def int16_safe(*values):
    return all(almost_equal(v, int(v)) and MIN_INT16 <= v <= MAX_INT16 for v in values)


def f2dot14_safe(*values):
    return all(MIN_F2DOT14 <= value <= MAX_F2DOT14 for value in values)


def fixed_safe(*values):
    return all(MIN_FIXED <= value <= MAX_FIXED for value in values)


def f2dot14_rotation_safe(*values):
    return all(MIN_F2DOT14 <= (value / 180.0) <= MAX_F2DOT14 for value in values)
