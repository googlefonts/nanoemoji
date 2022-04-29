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

from absl import flags
import pytest
from test_helper import active_temp_dirs, cleanup_temp_dirs, forget_temp_dirs


@pytest.fixture(autouse=True)
def absl_flags():
    flags.FLAGS(["unittest"])


# https://docs.pytest.org/en/latest/example/simple.html#making-test-result-information-available-in-fixtures
@pytest.hookimpl(tryfirst=True, hookwrapper=True)
def pytest_runtest_makereport(item, call):
    # execute all other hooks to obtain the report object
    outcome = yield
    result = outcome.get_result()
    attr_name = result.when + "_result"
    setattr(item, attr_name, result)


@pytest.fixture(autouse=True, scope="function")
def _cleanup_temporary_dirs(request):
    # The mkdtemp() docs say the user is responsible for deleting the directory
    # and its contents when done with it. So we use an autouse fixture that
    # automatically removes all the temp dirs at the end of the test module
    yield
    # teardown happens after the 'yield'
    if request.node.setup_result.passed and request.node.call_result.passed:
        print(f"Cleaning up {len(active_temp_dirs())} temp dirs")
        # assert False
        cleanup_temp_dirs()
    else:
        print(
            f"NOT cleaning up {len(active_temp_dirs())} temp dirs to ease troubleshooting"
        )
    forget_temp_dirs()
