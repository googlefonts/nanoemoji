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


def int16_safe(*values):
    return all(almost_equal(v, int(v)) and v <= 32767 and v >= -32768 for v in values)


def f2dot14_safe(*values):
    return all(value >= -2.0 and value < 2.0 for value in values)


def f2dot14_rotation_safe(*values):
    return all((value / 180.0) >= -2.0 and (value / 180.0) < 2.0 for value in values)